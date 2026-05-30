"""Live order manager: real Kalshi /portfolio/orders integration.

PARALLEL to PaperOrderManager. Same persistence + state pattern,
different endpoints. Live state lives at data/live_trades/state.json
(NOT data/paper_trades/state.json), per critic finding 3 (avoid
operator confusion).

Critic-required design points:

1. **Persisted UUID intent IDs** (critic finding 1). The intent is
   written to state.json BEFORE the first POST attempt; the same
   client_order_id is reused across all retries of that intent.
   Removes the minute-boundary race window.
2. **Idempotent fill processing** (critic finding 5). Track
   `processed_fill_ids`; skip fills already seen. On startup,
   reconcile from `last_reconciled_ts - 1h`.
3. **Stale-filled reconcile** (critic finding 6). Each loop polls
   GET /markets/{ticker} for every ticker in `state.filled_orders`,
   not just scanner candidates.

Kalshi endpoints used:
- POST /portfolio/orders: place maker bid.
- GET /portfolio/orders: list resting orders (by status / ticker).
- DELETE /portfolio/orders/{order_id}: cancel a resting order.
- GET /portfolio/fills: list fills since timestamp.
- GET /markets/{ticker}: check settlement.
- GET /portfolio/balance: pre-flight balance check (called by
  preflight module, not here).

Order body shape (POST /portfolio/orders):

    {
      "action": "buy",
      "side": "yes",
      "ticker": "KX...-...-T",
      "type": "limit",
      "count": 1,
      "yes_price": 75,                      # integer cents (1..99)
      "client_order_id": "<uuid hex 32ch>",
      "time_in_force": "good_til_cancel"
    }

If Kalshi later requires dollar strings instead of integer cents the
calling site can be updated; the wire format is centralized here.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from kalshi_bot.analysis.metrics import kalshi_maker_fee_per_contract
from kalshi_bot.risk.adverse_selection_monitor import (
    AdverseSelectionConfig,
    RestingOrderView,
    evaluate_resting_orders,
)

if TYPE_CHECKING:
    from kalshi_bot.data.kalshi_client import KalshiClient

log = structlog.get_logger(__name__)


class LiveOrderStatus(Enum):
    INTENT_RECORDED = "intent_recorded"  # state.json written; pre-POST
    LIVE_PENDING = "live_pending"        # POST sent, no ack yet (transient)
    LIVE_RESTING = "live_resting"        # Kalshi acked, order_id known
    LIVE_FILLED = "live_filled"          # fully filled; awaits settlement
    LIVE_PARTIAL = "live_partial"        # partially filled; still resting
    LIVE_CANCELLED = "live_cancelled"
    LIVE_VOIDED = "live_voided"          # market voided by Kalshi
    LIVE_SETTLED = "live_settled"


@dataclass
class LiveOrder:
    intent_id: str                       # UUID4 hex; also client_order_id
    ticker: str
    series_ticker: str
    event_ticker: str
    side: str                            # "yes" (this strategy only)
    target_price_cents: int              # 1..99
    contracts: int
    expected_net_edge: float
    market_mid_at_placement: float
    placed_ts: str
    status: LiveOrderStatus = LiveOrderStatus.INTENT_RECORDED
    order_id: str | None = None          # Kalshi-assigned, after ack
    acked_ts: str | None = None
    filled_ts: str | None = None
    filled_price_cents: int | None = None
    filled_count: int = 0
    cancelled_ts: str | None = None
    resolution_ts: str | None = None
    resolution_outcome: int | None = None  # 1 YES, 0 NO, -1 void
    realized_pnl_usd: float | None = None


@dataclass
class LiveState:
    """Persisted to data/live_trades/state.json."""

    intents: dict[str, LiveOrder] = field(default_factory=dict)
    resting: dict[str, LiveOrder] = field(default_factory=dict)
    filled: dict[str, LiveOrder] = field(default_factory=dict)
    closed: dict[str, LiveOrder] = field(default_factory=dict)
    processed_fill_ids: list[str] = field(default_factory=list)
    starting_bankroll_usd: float = 25.0
    realized_pnl_total_usd: float = 0.0
    last_reconciled_ts: str = ""
    last_updated_ts: str = ""


class LiveOrderManager:
    """Manage live Kalshi orders on disk and via REST.

    Concurrency: not thread-safe. Single-process invocation only.

    state_path defaults to data/live_trades/state.json. The path is
    different from PaperOrderManager (data/paper_trades/state.json) so
    operator inspection is unambiguous.
    """

    def __init__(
        self,
        client: KalshiClient,
        state_path: Path | None = None,
        intent_id_prefix: str = "",
    ) -> None:
        """
        intent_id_prefix: 2-character hex string baked into the first 2
        chars of every generated client_order_id. Lets operator (and
        diagnostic tools) identify order ownership purely from the Kalshi
        order_id, even if state.json is corrupted or wiped. Examples:
        '11' = v1 deep-favorite bot, '14' = v14 MLB-night daemon. Must be
        valid hex; default '' means no prefix (pure uuid4 hex, backward
        compatible).
        """
        if intent_id_prefix:
            if len(intent_id_prefix) > 8:
                raise ValueError(
                    f"intent_id_prefix must be <= 8 hex chars; got "
                    f"{len(intent_id_prefix)}: {intent_id_prefix!r}",
                )
            try:
                int(intent_id_prefix, 16)
            except ValueError as exc:
                raise ValueError(
                    f"intent_id_prefix must be hex; got {intent_id_prefix!r}",
                ) from exc
        self._client = client
        self._intent_id_prefix = intent_id_prefix.lower()
        self.state_path = state_path or Path("data/live_trades/state.json")
        self.state = self._load()

    def _new_intent_id(self) -> str:
        """Generate a 32-hex-char client_order_id. If `intent_id_prefix`
        is set, the first len(prefix) chars are replaced by the prefix
        so ownership is identifiable from the order_id alone.
        """
        raw = uuid.uuid4().hex
        if not self._intent_id_prefix:
            return raw
        n = len(self._intent_id_prefix)
        return self._intent_id_prefix + raw[n:]

    def _load(self) -> LiveState:
        if not self.state_path.exists():
            return LiveState()
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.error("live_state_corrupted", error=str(exc),
                      path=str(self.state_path))
            raise

        def _to_orders(d: dict) -> dict[str, LiveOrder]:
            return {
                k: LiveOrder(**{**v, "status": LiveOrderStatus(v["status"])})
                for k, v in d.items()
            }

        return LiveState(
            intents=_to_orders(raw.get("intents", {})),
            resting=_to_orders(raw.get("resting", {})),
            filled=_to_orders(raw.get("filled", {})),
            closed=_to_orders(raw.get("closed", {})),
            processed_fill_ids=list(raw.get("processed_fill_ids", [])),
            starting_bankroll_usd=raw.get("starting_bankroll_usd", 25.0),
            realized_pnl_total_usd=raw.get("realized_pnl_total_usd", 0.0),
            last_reconciled_ts=raw.get("last_reconciled_ts", ""),
            last_updated_ts=raw.get("last_updated_ts", ""),
        )

    def _save(self) -> None:
        def _orders_to_dict(d: dict[str, LiveOrder]) -> dict[str, dict]:
            return {k: {**asdict(o), "status": o.status.value} for k, o in d.items()}

        payload = {
            "intents": _orders_to_dict(self.state.intents),
            "resting": _orders_to_dict(self.state.resting),
            "filled": _orders_to_dict(self.state.filled),
            "closed": _orders_to_dict(self.state.closed),
            "processed_fill_ids": self.state.processed_fill_ids[-500:],
            "starting_bankroll_usd": self.state.starting_bankroll_usd,
            "realized_pnl_total_usd": self.state.realized_pnl_total_usd,
            "last_reconciled_ts": self.state.last_reconciled_ts,
            "last_updated_ts": datetime.now(UTC).isoformat(),
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.state_path)

    def place_live_order(
        self,
        *,
        ticker: str,
        series_ticker: str,
        event_ticker: str,
        target_price: float,
        contracts: int,
        expected_net_edge: float,
        market_mid_at_placement: float,
    ) -> LiveOrder:
        """Place a YES maker bid. Returns the LiveOrder record.

        Critical sequencing:
        1. Generate UUID intent_id.
        2. Build LiveOrder with INTENT_RECORDED status.
        3. Persist state.json BEFORE the POST attempt. (Crash-safety.)
        4. POST /portfolio/orders.
        5. On ack: store order_id, flip status to LIVE_RESTING, persist.
        6. On exception: leave INTENT_RECORDED in state.intents for
           the next reconcile pass. The persisted intent_id IS the
           client_order_id, so a retry uses the same id and Kalshi
           rejects-as-duplicate or fills-the-original-with-same-id.

        Returns the LiveOrder regardless of ack success; the caller
        inspects `.status` to learn what happened.
        """
        if contracts < 1:
            raise ValueError(f"contracts must be >= 1, got {contracts}")
        target_price_cents = int(round(target_price * 100))
        if not (1 <= target_price_cents <= 99):
            raise ValueError(
                f"target_price_cents out of range 1..99: {target_price_cents}",
            )

        intent_id = self._new_intent_id()
        ts = datetime.now(UTC).isoformat()
        order = LiveOrder(
            intent_id=intent_id,
            ticker=ticker,
            series_ticker=series_ticker,
            event_ticker=event_ticker,
            side="yes",
            target_price_cents=target_price_cents,
            contracts=contracts,
            expected_net_edge=expected_net_edge,
            market_mid_at_placement=market_mid_at_placement,
            placed_ts=ts,
        )

        # Persist BEFORE POST.
        self.state.intents[intent_id] = order
        self._save()

        # Kalshi REST API order body. Probed live 2026-05-23: the only
        # valid `time_in_force` enum values are `immediate_or_cancel` and
        # `good_till_canceled` (American spelling, snake_case). `EOD`,
        # `IOC`, `FOK`, and `good_til_cancelled` are all rejected with
        # `oneof` validation. We want a resting maker bid, so GTC fits.
        # `expiration_ts: 0` was rejected as EXPIRED_TIMESTAMP (epoch
        # zero = 1970). See scripts/probe_order_tif.py for the probe.
        body = {
            "action": "buy",
            "side": "yes",
            "ticker": ticker,
            "type": "limit",
            "count": contracts,
            "yes_price": target_price_cents,
            "client_order_id": intent_id,
            "time_in_force": "good_till_canceled",
        }

        try:
            order.status = LiveOrderStatus.LIVE_PENDING
            response = self._client.post("/portfolio/orders", json=body)
        except Exception as exc:
            log.error(
                "live_order_post_failed",
                intent_id=intent_id, ticker=ticker, error=str(exc),
            )
            # Leave order in INTENT_RECORDED / LIVE_PENDING; reconcile_resting()
            # will look this up by client_order_id on the next loop.
            order.status = LiveOrderStatus.INTENT_RECORDED
            self._save()
            return order

        # Successful ack. Pull order_id from response.
        order_data = response.get("order", {})
        kalshi_order_id = order_data.get("order_id") or order_data.get("id")
        if not kalshi_order_id:
            log.error(
                "live_order_ack_missing_order_id",
                intent_id=intent_id, ticker=ticker, response=response,
            )
            order.status = LiveOrderStatus.INTENT_RECORDED
            self._save()
            return order

        order.order_id = kalshi_order_id
        order.acked_ts = datetime.now(UTC).isoformat()
        # If Kalshi already marked it filled (FOK/IOC path; not our default),
        # transition straight to filled.
        kalshi_status = (order_data.get("status") or "").lower()
        if kalshi_status in ("filled", "executed"):
            order.status = LiveOrderStatus.LIVE_FILLED
            order.filled_ts = order.acked_ts
            order.filled_count = contracts
            order.filled_price_cents = target_price_cents
            self.state.filled[intent_id] = order
        else:
            order.status = LiveOrderStatus.LIVE_RESTING
            self.state.resting[intent_id] = order
        # Remove from intents (it's now in resting or filled).
        del self.state.intents[intent_id]
        self._save()
        log.info(
            "live_order_placed",
            intent_id=intent_id, order_id=kalshi_order_id, ticker=ticker,
            yes_price_cents=target_price_cents, contracts=contracts,
        )
        return order

    def reconcile_intents(self) -> list[LiveOrder]:
        """For each INTENT_RECORDED / LIVE_PENDING, ask Kalshi if it knows
        about the client_order_id. Resolves the lost-ack case.

        Returns the list of intents whose status changed.
        """
        changed: list[LiveOrder] = []
        for intent_id, order in list(self.state.intents.items()):
            try:
                # Kalshi exposes resting orders via /portfolio/orders. We
                # filter by client_order_id when supported; otherwise
                # paginate and match locally.
                results = list(self._client.paginate(
                    "/portfolio/orders", item_key="orders", limit=100,
                    client_order_id=intent_id, max_pages=2,
                ))
            except Exception as exc:
                log.warning(
                    "live_intent_lookup_failed",
                    intent_id=intent_id, error=str(exc),
                )
                continue
            found = [r for r in results
                     if r.get("client_order_id") == intent_id]
            if not found:
                # Kalshi never accepted it. Cancel locally (caller can retry).
                order.status = LiveOrderStatus.LIVE_CANCELLED
                order.cancelled_ts = datetime.now(UTC).isoformat()
                self.state.closed[intent_id] = order
                del self.state.intents[intent_id]
                changed.append(order)
                log.info("live_intent_orphan_cleared",
                         intent_id=intent_id, ticker=order.ticker)
                continue
            kalshi_record = found[0]
            order.order_id = kalshi_record.get("order_id") or kalshi_record.get("id")
            kalshi_status = (kalshi_record.get("status") or "").lower()
            order.acked_ts = datetime.now(UTC).isoformat()
            if kalshi_status in ("filled", "executed"):
                order.status = LiveOrderStatus.LIVE_FILLED
                order.filled_count = order.contracts
                order.filled_price_cents = order.target_price_cents
                order.filled_ts = order.acked_ts
                self.state.filled[intent_id] = order
            elif kalshi_status in ("cancelled", "canceled"):
                order.status = LiveOrderStatus.LIVE_CANCELLED
                order.cancelled_ts = order.acked_ts
                self.state.closed[intent_id] = order
            else:
                order.status = LiveOrderStatus.LIVE_RESTING
                self.state.resting[intent_id] = order
            del self.state.intents[intent_id]
            changed.append(order)
        if changed:
            self._save()
        return changed

    def reconcile_resting(self) -> list[LiveOrder]:
        """Cross-check each locally-resting order against Kalshi.

        Detects externally-changed resting orders that reconcile_fills
        can miss:
        - Operator-cancelled orders (via Kalshi UI or our cancel script)
        - Filled orders where reconcile_fills had a parsing bug
        - Voided orders Kalshi cancelled
        - Race conditions between our cancel script and the bot's saves

        For each locally-resting order, query Kalshi by client_order_id.
        If Kalshi returns no record, the order is gone (cancelled). If
        Kalshi reports it filled, move to LIVE_FILLED. If Kalshi reports
        it still resting, no-op.

        Returns the list of orders whose status changed.
        """
        changed: list[LiveOrder] = []
        for intent_id, order in list(self.state.resting.items()):
            try:
                results = list(self._client.paginate(
                    "/portfolio/orders", item_key="orders", limit=100,
                    client_order_id=intent_id, max_pages=2,
                ))
            except Exception as exc:
                log.warning(
                    "live_resting_lookup_failed",
                    intent_id=intent_id, error=str(exc),
                )
                continue
            found = [r for r in results
                     if r.get("client_order_id") == intent_id]
            if not found:
                # Kalshi has no record under our coid. The order is
                # gone. Could be cancelled or filled-then-purged.
                # /portfolio/fills already runs and would catch a fill,
                # so if we got here without a fill being applied, treat
                # as cancelled.
                order.status = LiveOrderStatus.LIVE_CANCELLED
                order.cancelled_ts = datetime.now(UTC).isoformat()
                self.state.closed[intent_id] = order
                del self.state.resting[intent_id]
                changed.append(order)
                log.info(
                    "live_resting_reconciled_as_cancelled",
                    intent_id=intent_id, ticker=order.ticker,
                )
                continue
            kalshi_record = found[0]
            kalshi_status = (kalshi_record.get("status") or "").lower()
            if kalshi_status in ("filled", "executed"):
                order.status = LiveOrderStatus.LIVE_FILLED
                order.filled_count = order.contracts
                order.filled_price_cents = order.target_price_cents
                order.filled_ts = datetime.now(UTC).isoformat()
                self.state.filled[intent_id] = order
                del self.state.resting[intent_id]
                changed.append(order)
                log.info(
                    "live_resting_reconciled_as_filled",
                    intent_id=intent_id, ticker=order.ticker,
                )
            elif kalshi_status in ("cancelled", "canceled"):
                order.status = LiveOrderStatus.LIVE_CANCELLED
                order.cancelled_ts = datetime.now(UTC).isoformat()
                self.state.closed[intent_id] = order
                del self.state.resting[intent_id]
                changed.append(order)
                log.info(
                    "live_resting_reconciled_as_cancelled",
                    intent_id=intent_id, ticker=order.ticker,
                )
            # else: still resting, no change needed.
        if changed:
            self._save()
        return changed

    def reconcile_fills(self) -> list[LiveOrder]:
        """Pull recent fills from /portfolio/fills and apply them to
        resting orders. Idempotent: same fill_id is never applied twice.

        On startup the look-back window covers `last_reconciled_ts - 1h`
        to handle crash-during-reconcile (critic finding 5).
        """
        now = datetime.now(UTC)
        look_back = self._look_back_ts()
        try:
            raw_fills = list(self._client.paginate(
                "/portfolio/fills", item_key="fills", limit=200,
                min_ts=look_back, max_pages=10,
            ))
        except Exception as exc:
            log.warning("live_fills_fetch_failed", error=str(exc))
            return []

        seen = set(self.state.processed_fill_ids)
        changed: list[LiveOrder] = []
        for fill in raw_fills:
            fill_id = fill.get("trade_id") or fill.get("id")
            if not fill_id or fill_id in seen:
                continue
            order_id = fill.get("order_id")
            order = self._find_resting_by_order_id(order_id)
            if order is None:
                # A fill for an order we didn't place / aren't tracking.
                # Could be from a prior bot run or a manual operator
                # action; mark fill as processed so we don't reprocess.
                self.state.processed_fill_ids.append(fill_id)
                seen.add(fill_id)
                continue
            # Kalshi /portfolio/fills returns `count_fp` (fixed-point
            # string) and `yes_price_dollars` (dollar string) per the
            # post-March-2026 API. Older `count` / `yes_price` integer
            # fields are NOT present. Bug fixed 2026-05-23 after a real
            # fill (SAS playoff wins) parsed as count=0 and got stuck
            # in LIVE_PARTIAL forever. Fall back to the older field
            # names if the new ones are absent.
            count_raw = fill.get("count_fp") if "count_fp" in fill else fill.get("count")
            try:
                filled_count_this = int(round(float(count_raw))) if count_raw is not None else 0
            except (TypeError, ValueError):
                filled_count_this = 0
            price_raw = fill.get("yes_price_dollars")
            if price_raw is not None:
                try:
                    filled_price_cents = int(round(float(price_raw) * 100))
                except (TypeError, ValueError):
                    filled_price_cents = order.target_price_cents
            else:
                try:
                    filled_price_cents = int(fill.get("yes_price", order.target_price_cents))
                except (TypeError, ValueError):
                    filled_price_cents = order.target_price_cents
            order.filled_count += filled_count_this
            order.filled_price_cents = filled_price_cents
            order.filled_ts = fill.get("created_time") or now.isoformat()
            if order.filled_count >= order.contracts:
                order.status = LiveOrderStatus.LIVE_FILLED
                self.state.filled[order.intent_id] = order
                del self.state.resting[order.intent_id]
            else:
                order.status = LiveOrderStatus.LIVE_PARTIAL
            self.state.processed_fill_ids.append(fill_id)
            seen.add(fill_id)
            changed.append(order)
            log.info(
                "live_fill_applied",
                intent_id=order.intent_id, fill_id=fill_id, ticker=order.ticker,
                filled_count_this=filled_count_this,
                cumulative_filled=order.filled_count,
            )

        self.state.last_reconciled_ts = now.isoformat()
        if changed:
            self._save()
        else:
            # Touch state to update last_reconciled_ts even with no fills.
            self._save()
        return changed

    def reconcile_settlements(self) -> list[LiveOrder]:
        """For every filled order not yet settled, GET /markets/{ticker}
        and check if it has resolved (critic finding 6).

        Returns the list of newly-settled orders.
        """
        settled: list[LiveOrder] = []
        for intent_id, order in list(self.state.filled.items()):
            try:
                response = self._client.get(f"/markets/{order.ticker}")
            except Exception as exc:
                log.warning(
                    "live_market_fetch_failed",
                    ticker=order.ticker, error=str(exc),
                )
                continue
            market = response.get("market", {}) or {}
            status = (market.get("status") or "").lower()
            # Kalshi's terminal resolved status on the live API is
            # "finalized" (verified against the prod API, 2026-05-30 UTC);
            # "settled" is accepted defensively in case the convention
            # changes. Every other status (including the intermediate
            # "determined" state, where the result is known but the ~120s
            # settlement timer has not elapsed) is left for a later loop.
            if status not in ("finalized", "settled"):
                continue
            # A market in a terminal status MUST be settled now so its
            # capital is released. yes/no map to win/loss; ANY other result
            # (an explicit "void", a non-binary token like "scalar", or an
            # unexpected/empty value) is treated as void (return to entry,
            # fees only). Never leave a terminal market in `filled`, or its
            # exposure strands forever (the bug this method is fixing).
            result = (market.get("result") or "").strip().lower()
            if result == "yes":
                outcome = 1
            elif result == "no":
                outcome = 0
            else:
                outcome = -1  # void / scalar / unrecognized: refund-to-entry
                if result != "void":
                    log.warning(
                        "live_settlement_unrecognized_result",
                        ticker=order.ticker, status=status, result=result,
                    )
            order.resolution_outcome = outcome
            order.resolution_ts = (
                market.get("settlement_ts")
                or market.get("settled_time")
                or market.get("close_time")
                or datetime.now(UTC).isoformat()
            )
            order.realized_pnl_usd = self._compute_realized_pnl(order, outcome)
            order.status = LiveOrderStatus.LIVE_SETTLED
            self.state.realized_pnl_total_usd += order.realized_pnl_usd
            self.state.closed[intent_id] = order
            del self.state.filled[intent_id]
            settled.append(order)
            log.info(
                "live_order_settled",
                intent_id=intent_id, ticker=order.ticker,
                outcome=outcome, pnl_usd=order.realized_pnl_usd,
            )
        if settled:
            self._save()
        return settled

    def cancel_all_resting(self) -> list[str]:
        """Best-effort cancel for every order in `state.resting`.

        Used by the SIGINT/SIGTERM handler. Returns the list of
        intent_ids successfully cancelled. Failures are logged but
        don't raise.
        """
        cancelled: list[str] = []
        for intent_id, order in list(self.state.resting.items()):
            if not order.order_id:
                continue
            try:
                self._client.delete(f"/portfolio/orders/{order.order_id}")
            except Exception as exc:
                log.warning(
                    "live_cancel_failed",
                    intent_id=intent_id, order_id=order.order_id,
                    error=str(exc),
                )
                continue
            order.status = LiveOrderStatus.LIVE_CANCELLED
            order.cancelled_ts = datetime.now(UTC).isoformat()
            self.state.closed[intent_id] = order
            del self.state.resting[intent_id]
            cancelled.append(intent_id)
        if cancelled:
            self._save()
        return cancelled

    def cancel_stale_resting(self, *, max_age_hours: float) -> list[str]:
        """Cancel resting orders older than `max_age_hours` to free up
        budget for fresh opportunities.

        Why: maker bids on Kalshi do NOT lock cash on the exchange side,
        so the bot can stack 60+ unfilled $0.70 bids in markets where
        the offer is $0.80+. Those bids sit forever, never fill, and
        consume our local-side budget against `cash`. Periodic stale-
        bid sweep recycles that budget.

        Uses `placed_ts` (ISO string) as the age clock. Orders without
        a parseable placed_ts are left alone (cautious default).
        """
        if max_age_hours <= 0:
            return []
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=max_age_hours)
        cancelled: list[str] = []
        for intent_id, order in list(self.state.resting.items()):
            if not order.order_id:
                continue
            try:
                placed = datetime.fromisoformat(order.placed_ts)
            except (ValueError, TypeError):
                continue
            if placed > cutoff:
                continue
            try:
                self._client.delete(f"/portfolio/orders/{order.order_id}")
            except Exception as exc:
                log.warning(
                    "live_cancel_stale_failed",
                    intent_id=intent_id, order_id=order.order_id,
                    error=str(exc),
                )
                continue
            order.status = LiveOrderStatus.LIVE_CANCELLED
            order.cancelled_ts = now.isoformat()
            self.state.closed[intent_id] = order
            del self.state.resting[intent_id]
            cancelled.append(intent_id)
            log.info(
                "live_stale_resting_cancelled",
                intent_id=intent_id, ticker=order.ticker,
                placed_ts=order.placed_ts, age_hours=round(
                    (now - placed).total_seconds() / 3600.0, 2,
                ),
            )
        if cancelled:
            self._save()
        return cancelled

    def reconcile_adverse_selection(
        self,
        *,
        config: AdverseSelectionConfig | None = None,
    ) -> list[str]:
        """Cancel resting orders where the live orderbook mid has drifted
        materially against the resting bid price.

        Round 15b addition (2026-05-27): live observation found mean
        post-fill mid drift of -4.93pp across 15 still-open v1 fills,
        with 9 of 15 drifting against the maker bid. This method pulls
        the current orderbook mid for every locally-resting ticker,
        feeds resting orders through evaluate_resting_orders, and acts
        on each CancelRecommendation by DELETEing the Kalshi order.

        Failures pulling individual orderbooks are logged and skipped;
        a single ticker's API failure does NOT abort the whole pass.

        Returns the list of intent_ids successfully cancelled.
        """
        if not self.state.resting:
            return []
        cfg = config or AdverseSelectionConfig()
        order_views: list[RestingOrderView] = []
        mids_by_ticker: dict[str, float] = {}
        for intent_id, order in self.state.resting.items():
            order_views.append(RestingOrderView(
                intent_id=intent_id,
                ticker=order.ticker,
                side=order.side,
                target_price_cents=order.target_price_cents,
                placed_ts=order.placed_ts,
            ))
            if order.ticker in mids_by_ticker:
                continue
            mid_cents = self._fetch_orderbook_mid_cents(order.ticker)
            if mid_cents is not None:
                mids_by_ticker[order.ticker] = mid_cents

        recs = evaluate_resting_orders(
            order_views,
            mids_by_ticker,
            config=cfg,
            now_iso=datetime.now(UTC).isoformat(),
        )
        cancelled: list[str] = []
        for rec in recs:
            order = self.state.resting.get(rec.intent_id)
            if order is None or not order.order_id:
                continue
            try:
                self._client.delete(f"/portfolio/orders/{order.order_id}")
            except Exception as exc:
                log.warning(
                    "adverse_selection_cancel_failed",
                    intent_id=rec.intent_id, order_id=order.order_id,
                    ticker=order.ticker, error=str(exc),
                )
                continue
            order.status = LiveOrderStatus.LIVE_CANCELLED
            order.cancelled_ts = datetime.now(UTC).isoformat()
            self.state.closed[rec.intent_id] = order
            del self.state.resting[rec.intent_id]
            cancelled.append(rec.intent_id)
            log.info(
                "adverse_selection_cancel",
                intent_id=rec.intent_id, order_id=order.order_id,
                ticker=order.ticker,
                target_price_cents=rec.target_price_cents,
                current_mid_cents=rec.current_mid_cents,
                drift_cents=rec.drift_cents,
                reason=rec.reason,
            )
        if cancelled:
            self._save()
        return cancelled

    def _fetch_orderbook_mid_cents(self, ticker: str) -> float | None:
        """Pull /markets/{ticker}/orderbook and return the YES mid in cents.

        Returns None when the call fails, the response shape is unexpected,
        or the book is one-sided (no mid is computable). All exceptions are
        swallowed so the caller's loop survives transient API failures.
        """
        try:
            payload = self._client.get(f"/markets/{ticker}/orderbook")
        except Exception as exc:
            log.warning(
                "adverse_selection_orderbook_fetch_failed",
                ticker=ticker, error=str(exc),
            )
            return None
        try:
            ob = payload.get("orderbook_fp", {}) or {}
            yes_levels = ob.get("yes_dollars", []) or []
            no_levels = ob.get("no_dollars", []) or []
            if not yes_levels or not no_levels:
                return None
            yes_bid = max(float(p) for p, _sz in yes_levels)
            no_bid = max(float(p) for p, _sz in no_levels)
            yes_ask = 1.0 - no_bid
            mid_dollars = (yes_bid + yes_ask) / 2.0
            return mid_dollars * 100.0
        except (TypeError, ValueError, KeyError) as exc:
            log.warning(
                "adverse_selection_orderbook_parse_failed",
                ticker=ticker, error=str(exc),
            )
            return None

    def _find_resting_by_order_id(self, order_id: str | None) -> LiveOrder | None:
        if not order_id:
            return None
        for o in self.state.resting.values():
            if o.order_id == order_id:
                return o
        return None

    def _look_back_ts(self) -> int:
        """Compute the min_ts for fill polling, as Unix epoch SECONDS.

        Kalshi's /portfolio/fills endpoint validates `min_ts` as an
        integer (Go's `strconv.ParseInt`); ISO-formatted strings are
        rejected with HTTP 400 (verified live 2026-05-23).

        On normal loop iteration: last_reconciled_ts - 1h (overlap
        protects against crash-during-reconcile).
        On startup or after long downtime: 24h ago.
        """
        if not self.state.last_reconciled_ts:
            t = datetime.now(UTC) - timedelta(hours=24)
            return int(t.timestamp())
        try:
            last = datetime.fromisoformat(self.state.last_reconciled_ts)
        except ValueError:
            t = datetime.now(UTC) - timedelta(hours=24)
            return int(t.timestamp())
        return int((last - timedelta(hours=1)).timestamp())

    def _compute_realized_pnl(self, order: LiveOrder, outcome: int) -> float:
        if order.filled_price_cents is None:
            return 0.0
        price = order.filled_price_cents / 100.0
        if outcome == 1:
            payoff = 1.0 - price
        elif outcome == 0:
            payoff = -price
        else:
            # Void: return to entry. Net is zero before fees; we still pay
            # the entry maker fee.
            payoff = 0.0
        fee = 2.0 * kalshi_maker_fee_per_contract(price)
        pnl_per_contract = payoff - fee
        return pnl_per_contract * order.filled_count

    def current_live_bankroll(self) -> float:
        return self.state.starting_bankroll_usd + self.state.realized_pnl_total_usd

    def total_resting_exposure_usd(self) -> float:
        return sum(
            (o.target_price_cents / 100.0) * (o.contracts - o.filled_count)
            for o in self.state.resting.values()
        )

    def open_order_count(self) -> int:
        """Total live positions: intents pending POST + resting on book +
        filled awaiting settlement. Used by the loop to gate new
        placements against max_concurrent. Includes filled because
        their capital is still committed; excluding them allowed
        capital to escape the cap as positions filled (bug fixed
        post-go-live, 2026-05-23).
        """
        return (
            len(self.state.resting)
            + len(self.state.intents)
            + len(self.state.filled)
        )

    def _convert_dict_for_state(
        self, src: dict[str, dict[str, Any]],
    ) -> dict[str, LiveOrder]:
        """Helper kept for parity with PaperOrderManager test patterns."""
        return {
            k: LiveOrder(**{**v, "status": LiveOrderStatus(v["status"])})
            for k, v in src.items()
        }
