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
- POST /portfolio/events/orders: place maker bid (V2 single-book; the
  legacy /portfolio/orders create endpoint was deprecated and removed
  2026-06, returning HTTP 410 deprecated_v1_order_endpoint).
- GET /portfolio/orders: list resting orders (by status / ticker).
- DELETE /portfolio/events/orders/{order_id}: cancel a resting order (V2
  single-book; the legacy DELETE /portfolio/orders/{order_id} mutation is
  being deprecated 2026-06-18..25 alongside the create endpoint).
- GET /portfolio/fills: list fills since timestamp.
- GET /markets/{ticker}: check settlement.
- GET /portfolio/balance: pre-flight balance check (called by
  preflight module, not here).

Order body shape (POST /portfolio/events/orders, Kalshi V2 single-book):

    {
      "ticker": "KX...-...-T",
      "side": "bid",                         # bid = buy YES; ask = sell YES
      "count": "1",                          # fixed-point contract string
      "price": "0.75",                       # fixed-point YES-side dollars
      "client_order_id": "<uuid hex 32ch>",
      "time_in_force": "good_till_canceled",
      "self_trade_prevention_type": "taker_at_cross"
    }

The book is quoted entirely from the YES side: a YES-favorite bid is
side="bid" at the YES price; a NO-underdog bid is side="ask" at the
YES-equivalent price (1 - no_price). The legacy /portfolio/orders body
(action/side=yes|no/yes_price|no_price in integer cents) was deprecated
and removed 2026-06. The wire format is centralized in place_live_order.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

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
    fee_cost_usd: float = 0.0              # actual Kalshi fees on fills (USD)
    cancelled_ts: str | None = None
    resolution_ts: str | None = None
    resolution_outcome: int | None = None  # 1 YES, 0 NO, -1 void
    realized_pnl_usd: float | None = None
    stuck_alert_ts: str | None = None      # set once when flagged stuck


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
    # Display-only cutoff (research/v20): when set, the reported running-total
    # tally counts only settled bets PLACED at/after this ISO timestamp, so a
    # strategy/universe change (e.g. the allowlist + sizing changes) can be
    # evaluated cleanly without old broad-universe bets. Does NOT affect
    # realized_pnl_total_usd (the all-time accumulator feeding current_live_
    # bankroll), exposure, settlement, or the kill triggers. None = count all.
    tally_since_ts: str | None = None
    last_reconciled_ts: str = ""
    last_updated_ts: str = ""


def _parse_iso(ts: str | None) -> datetime | None:
    """Parse an ISO timestamp to a tz-aware UTC datetime; None if unparseable.

    Accepts both the '+00:00' and 'Z' suffixes and treats a naive timestamp as
    UTC, so comparisons against the (tz-aware) cutoff never raise.
    """
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


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
            tally_since_ts=raw.get("tally_since_ts"),
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
            "tally_since_ts": self.state.tally_since_ts,
            "last_reconciled_ts": self.state.last_reconciled_ts,
            "last_updated_ts": datetime.now(UTC).isoformat(),
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        # Atomic replace, with retry on transient Windows file locks. This dir
        # lives under OneDrive, which intermittently holds state.json open while
        # syncing it (WinError 5 "Access is denied" on the rename); AV scans can
        # too. Mirrors the kill_state append retry. The loop's own try/except
        # already prevents a crash, but retrying avoids skipping the persist on
        # a sync collision (which left a stale state.tmp on 2026-06-19).
        for attempt in range(6):
            try:
                tmp.replace(self.state_path)
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.5)

    def realized_summary_since(
        self, since_ts: str | None,
    ) -> tuple[float, int, int, int, int]:
        """Summarize settled bets for the running-total display.

        Returns (realized_pnl_usd, winners, losers, voids, count) over settled
        orders in the closed bucket whose placed_ts is at/after `since_ts`. When
        `since_ts` is None or unparseable, counts ALL settled orders (the
        prior behavior). Keyed on placed_ts (when the bet was made), so a bet
        placed before the cutoff but settling after it is correctly EXCLUDED.

        W/L is SIDE-AWARE (matches the kill trigger's favorite_won): a bet wins
        when the side it bought won, i.e. a YES bet resolving YES (outcome 1) OR
        a NO bet resolving NO (outcome 0). Without this, the NO-underdog arm's
        wins and losses are inverted (a NO bet resolving NO would be miscounted
        as a loss). Voids are outcome -1.

        Display-only: reads the actual settled records and is independent of
        realized_pnl_total_usd, exposure, settlement, and the kill triggers.
        """
        cutoff = _parse_iso(since_ts) if since_ts else None
        total = 0.0
        winners = losers = voids = 0
        for o in self.state.closed.values():
            if o.realized_pnl_usd is None:
                continue  # not settled (e.g. cancelled, no P&L)
            if cutoff is not None:
                placed = _parse_iso(o.placed_ts)
                if placed is None or placed < cutoff:
                    continue
            total += o.realized_pnl_usd
            if o.resolution_outcome == -1:
                voids += 1
            elif (
                (o.side == "yes" and o.resolution_outcome == 1)
                or (o.side == "no" and o.resolution_outcome == 0)
            ):
                winners += 1
            elif o.resolution_outcome in (0, 1):
                losers += 1
        return total, winners, losers, voids, winners + losers + voids

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
        side: str = "yes",
    ) -> LiveOrder:
        """Place a maker bid on `side` ("yes" or "no"). Returns the LiveOrder.

        `side` defaults to "yes" (the classic deep-favorite arm). "no" places a
        NO maker bid at `target_price` in NO terms (the v18 underdog arm: when a
        market is framed as the underdog's YES, the favorite is the NO side).
        target_price is always the price OF THE BID'S OWN SIDE (yes_price for a
        yes bid, no_price for a no bid).

        Critical sequencing:
        1. Generate UUID intent_id.
        2. Build LiveOrder with INTENT_RECORDED status.
        3. Persist state.json BEFORE the POST attempt. (Crash-safety.)
        4. POST /portfolio/events/orders.
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
        if side not in ("yes", "no"):
            raise ValueError(f"side must be 'yes' or 'no', got {side!r}")
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
            side=side,
            target_price_cents=target_price_cents,
            contracts=contracts,
            expected_net_edge=expected_net_edge,
            market_mid_at_placement=market_mid_at_placement,
            placed_ts=ts,
        )

        # Persist BEFORE POST.
        self.state.intents[intent_id] = order
        self._save()

        # Kalshi V2 single-book order body. The legacy /portfolio/orders
        # create endpoint (action/side=yes|no/yes_price|no_price in cents) was
        # deprecated and removed 2026-06 (HTTP 410 deprecated_v1_order_endpoint);
        # V2 /portfolio/events/orders is now required.
        #
        # The V2 book is quoted ENTIRELY from the YES side:
        #   side="bid" buys YES; side="ask" sells YES (== buys NO at 1 - price).
        # Our two arms map onto that single book as:
        #   favorite YES arm (side=="yes"): bid at the YES price.
        #   no-underdog arm  (side=="no") : ask at the YES-EQUIVALENT price,
        #     i.e. (100 - target_price_cents) cents, because buying NO at
        #     no_price is economically selling YES at (1 - no_price).
        # target_price_cents is always the bid's OWN-side price (validated
        # 1..99 above), so yes_price_cents stays in 1..99 for both arms.
        #
        # price/count are fixed-point DOLLAR/contract STRINGS, not cents.
        # time_in_force good_till_canceled preserves the resting-maker behavior
        # (probed 2026-05-23: only immediate_or_cancel and good_till_canceled
        # are valid). self_trade_prevention_type is REQUIRED by V2;
        # taker_at_cross is the documented default and our event-level dedup
        # means self-crosses do not arise in practice. post_only is left unset
        # to preserve legacy behavior (a crossing bid may fill immediately).
        if side == "yes":
            v2_side = "bid"
            yes_price_cents = target_price_cents
        else:  # side == "no": buy NO at target_price_cents == sell YES at (100 - it)
            v2_side = "ask"
            yes_price_cents = 100 - target_price_cents
        price_dollars = f"{yes_price_cents // 100}.{yes_price_cents % 100:02d}"
        body = {
            "ticker": ticker,
            "side": v2_side,
            "count": str(contracts),
            "price": price_dollars,
            "time_in_force": "good_till_canceled",
            "self_trade_prevention_type": "taker_at_cross",
            "client_order_id": intent_id,
        }

        try:
            order.status = LiveOrderStatus.LIVE_PENDING
            response = self._client.post("/portfolio/events/orders", json=body)
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

        # V2 ack is a FLAT object (no nested "order"): order_id,
        # client_order_id, fill_count, remaining_count, average_fill_price,
        # average_fee_paid (all strings), ts_ms. There is no "status" field;
        # fill state is read from the counts.
        kalshi_order_id = response.get("order_id") or response.get("id")
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

        try:
            fill_count = float(response.get("fill_count") or 0)
        except (TypeError, ValueError):
            fill_count = 0.0
        try:
            remaining_count = float(response.get("remaining_count") or 0)
        except (TypeError, ValueError):
            remaining_count = 0.0
        # A pure good_till_canceled maker bid normally rests (fill_count 0). If
        # Kalshi reports a full immediate fill (fill_count > 0 and nothing
        # remaining), record it as filled. Any partial fill keeps the order
        # RESTING so reconcile_fills / reconcile_resting pick up the remainder.
        # NOTE: this straight-to-filled path does NOT capture the actual fee
        # (fee_cost lives on the /portfolio/fills record, not the order ack, and
        # reconcile_fills only matches RESTING orders), so such an order would
        # keep fee_cost_usd=0. This is acceptable because v1 is a pure GTC maker
        # whose fills normally arrive via reconcile_fills (resting -> filled),
        # where the real fee IS captured; an immediate full fill is a non-default
        # edge case. Revisit if an IOC/FOK arm is ever added.
        if fill_count > 0 and remaining_count <= 0:
            order.status = LiveOrderStatus.LIVE_FILLED
            order.filled_ts = order.acked_ts
            # A full immediate fill means all placed contracts filled. Use the
            # placed count (robust to the ack's fill_count string format and
            # identical to the legacy behavior).
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
            side=v2_side, yes_price_cents=yes_price_cents,
            own_side_price_cents=target_price_cents, contracts=contracts,
            fill_count=fill_count, remaining_count=remaining_count,
        )
        return order

    @staticmethod
    def _order_lookup_params(order: LiveOrder) -> dict[str, Any]:
        """Query params for finding `order` via GET /portfolio/orders.

        Scope by ticker (a server-supported filter, "Filter by market ticker")
        and drain that one market fully (max_pages=None), so a not-found
        verdict is real rather than a pagination-truncation artifact. A finite
        page cap is deliberately NOT used on the ticker path: it would reinstate
        a (larger) version of the very windowing bug this fixes if Kalshi ever
        sorted a heavily re-quoted market oldest-first. This strategy places
        about one bid per market, so a scoped query returns only a handful of
        records and the drain terminates in a single page; full drain is what
        makes the not-found verdict trustworthy.
        client_order_id is NOT a supported query parameter here (Kalshi ignores
        it), so the lookup never relies on it server-side; callers match it
        locally. No status filter is applied: the lookup must see resting AND
        executed AND canceled records to read the current status of the order.
        The no-ticker branch is defensive only (placement always sets a ticker)
        and keeps a finite page cap so it can never drain the whole account.
        """
        if order.ticker:
            return {"ticker": order.ticker, "max_pages": None}
        return {"max_pages": 10}

    def reconcile_intents(self) -> list[LiveOrder]:
        """For each INTENT_RECORDED / LIVE_PENDING, ask Kalshi if it knows
        about the client_order_id. Resolves the lost-ack case.

        Returns the list of intents whose status changed.
        """
        changed: list[LiveOrder] = []
        for intent_id, order in list(self.state.intents.items()):
            try:
                # Look the order up scoped to its market (see
                # _order_lookup_params), then match our client_order_id
                # locally. Scoping by ticker bounds the page so an order
                # outside an unscoped first-page window can no longer be
                # missed and falsely cancelled.
                results = list(self._client.paginate(
                    "/portfolio/orders", item_key="orders", limit=100,
                    **self._order_lookup_params(order),
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
                # Scope by ticker and match client_order_id locally; see
                # _order_lookup_params and reconcile_intents for why an
                # unscoped client_order_id query is unreliable.
                results = list(self._client.paginate(
                    "/portfolio/orders", item_key="orders", limit=100,
                    **self._order_lookup_params(order),
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
            # Kalshi reports the fill price in YES terms; convert to the order's
            # OWN side so a NO order records its no_price (no_price = 100 -
            # yes_price). filled_price_cents must always be the bought contract's
            # price for _compute_realized_pnl to be correct.
            yes_cents: int | None = None
            price_raw = fill.get("yes_price_dollars")
            if price_raw is not None:
                try:
                    yes_cents = int(round(float(price_raw) * 100))
                except (TypeError, ValueError):
                    yes_cents = None
            if yes_cents is None:
                try:
                    yes_cents = int(fill.get("yes_price"))
                except (TypeError, ValueError):
                    yes_cents = None
            if yes_cents is None:
                filled_price_cents = order.target_price_cents
            else:
                filled_price_cents = (100 - yes_cents) if order.side == "no" else yes_cents
            order.filled_count += filled_count_this
            order.filled_price_cents = filled_price_cents
            order.filled_ts = fill.get("created_time") or now.isoformat()
            # Capture Kalshi's ACTUAL per-fill fee (a dollar string, e.g.
            # "0.005200"), summed across partial fills. This is the single
            # source of truth for realized-P&L fees: the bot no longer models
            # the maker-fee schedule, which over-deducted ~3-4x (verified
            # 2026-06-13 vs /portfolio/fills fee_cost: real ATP/WTA/MLB maker
            # fee ~0.4-0.7c/contract, the old model charged ~2c).
            try:
                order.fee_cost_usd += float(fill.get("fee_cost") or 0.0)
            except (TypeError, ValueError):
                pass
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

    def reconcile_stuck_positions(
        self, *, stuck_age_hours: float = 24.0,
    ) -> tuple[list[LiveOrder], list[LiveOrder]]:
        """Release or flag filled orders whose market never reached a
        terminal status (postponed game, voided-without-finalize, anomaly).

        Call AFTER reconcile_settlements: anything still in `filled` here was
        NOT finalized this pass. For orders filled longer than
        `stuck_age_hours`, consult /portfolio/positions (Kalshi truth):

        - Position flat (position_fp == 0, ticker PRESENT in the response):
          the market closed outside the finalized path. A real yes/no
          resolution would have finalized and been caught above, so a flat
          position here is a void/cancel. Settle as void (refund to entry,
          fees only) via the bot's own fee model, which keeps
          realized_pnl_total_usd single-writer-consistent with every other
          settlement.
        - Position still held, OR ticker ABSENT (UNKNOWN, never read a
          missing key as flat): leave in `filled` and flag once for an
          operator alert.

        Returns (settled_void, newly_flagged). NEVER voids on a timer alone;
        only when Kalshi confirms the position is flat.
        """
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=stuck_age_hours)
        candidates: list[tuple[str, LiveOrder]] = []
        for intent_id, order in self.state.filled.items():
            ref_ts = order.filled_ts or order.placed_ts
            try:
                ref = datetime.fromisoformat(ref_ts)
            except (ValueError, TypeError):
                continue
            if ref <= cutoff:
                candidates.append((intent_id, order))
        if not candidates:
            return [], []

        try:
            resp = self._client.get("/portfolio/positions")
        except Exception as exc:
            log.warning("live_positions_fetch_failed", error=str(exc))
            return [], []
        pos_by_ticker: dict[str, dict] = {
            p.get("ticker"): p
            for p in (resp.get("market_positions") or [])
            if p.get("ticker")
        }

        settled_void: list[LiveOrder] = []
        newly_flagged: list[LiveOrder] = []
        for intent_id, order in candidates:
            pos = pos_by_ticker.get(order.ticker)
            is_flat = False
            if pos is not None:
                try:
                    is_flat = int(round(float(pos.get("position_fp") or 0))) == 0
                except (TypeError, ValueError):
                    is_flat = False
            if is_flat:
                order.resolution_outcome = -1  # void: refund-to-entry
                order.resolution_ts = now.isoformat()
                order.realized_pnl_usd = self._compute_realized_pnl(order, -1)
                order.status = LiveOrderStatus.LIVE_VOIDED
                self.state.realized_pnl_total_usd += order.realized_pnl_usd
                self.state.closed[intent_id] = order
                del self.state.filled[intent_id]
                settled_void.append(order)
                log.info(
                    "live_stuck_position_void_settled",
                    intent_id=intent_id, ticker=order.ticker,
                    pnl_usd=order.realized_pnl_usd,
                )
            elif order.stuck_alert_ts is None:
                order.stuck_alert_ts = now.isoformat()
                newly_flagged.append(order)
                log.warning(
                    "live_stuck_position_flagged",
                    intent_id=intent_id, ticker=order.ticker,
                    filled_ts=order.filled_ts,
                )
        if settled_void or newly_flagged:
            self._save()
        return settled_void, newly_flagged

    def flag_stuck_past_close(
        self, *, min_hours_past_close: float = 48.0,
    ) -> list[LiveOrder]:
        """Alert-only stuck detection for a long-horizon book (v1).

        A filled order whose market is PAST its own close_time by
        `min_hours_past_close` but has NOT reached a terminal status is
        flagged ONCE (via stuck_alert_ts) for an operator alert. Unlike
        reconcile_stuck_positions (v14), this does NOT void or mutate P&L:
        for an operator-tracked season-long book, a silent auto-void of a
        months-long position is the wrong action; the operator decides.

        Gates on the market's close_time, NOT fill age, so a normal
        still-open long-horizon position (close_time in the future) is never
        flagged. Terminal markets are left to reconcile_settlements. A
        per-ticker fetch failure or a missing close_time is logged/skipped;
        it never flags on absent data.

        Returns the list of newly-flagged orders.
        """
        now = datetime.now(UTC)
        newly: list[LiveOrder] = []
        for intent_id, order in list(self.state.filled.items()):
            if order.stuck_alert_ts is not None:
                continue
            try:
                resp = self._client.get(f"/markets/{order.ticker}")
            except Exception as exc:
                log.warning(
                    "live_stuck_market_fetch_failed",
                    ticker=order.ticker, error=str(exc),
                )
                continue
            market = resp.get("market", {}) or {}
            status = (market.get("status") or "").lower()
            if status in ("finalized", "settled"):
                continue  # reconcile_settlements owns terminal markets
            close_str = market.get("close_time")
            if not close_str:
                continue
            try:
                close_dt = datetime.fromisoformat(
                    str(close_str).replace("Z", "+00:00"),
                )
            except (ValueError, TypeError):
                continue
            if now <= close_dt + timedelta(hours=min_hours_past_close):
                continue
            order.stuck_alert_ts = now.isoformat()
            newly.append(order)
            log.warning(
                "live_stuck_past_close_flagged",
                intent_id=intent_id, ticker=order.ticker, close_time=close_str,
            )
        if newly:
            self._save()
        return newly

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
                self._client.delete(f"/portfolio/events/orders/{order.order_id}")
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
                self._client.delete(f"/portfolio/events/orders/{order.order_id}")
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

    def cancel_resting_by_series(
        self, denylisted_series: frozenset[str] | set[str],
    ) -> list[str]:
        """Cancel resting (unfilled) orders whose series is denylisted.

        Cleans up bids on series the bot no longer trades (e.g. after a
        denylist update): an unfilled maker bid carries no position and locks
        no cash on Kalshi, so cancelling it is always safe. The series prefix
        is taken from the order's series_ticker, falling back to the substring
        before the first '-' in the ticker. Returns the cancelled intent_ids.
        """
        if not denylisted_series:
            return []
        now = datetime.now(UTC)
        cancelled: list[str] = []
        for intent_id, order in list(self.state.resting.items()):
            if not order.order_id:
                continue
            prefix = order.series_ticker or order.ticker.partition("-")[0]
            if prefix not in denylisted_series:
                continue
            try:
                self._client.delete(f"/portfolio/events/orders/{order.order_id}")
            except Exception as exc:
                log.warning(
                    "live_cancel_denylist_failed",
                    intent_id=intent_id, order_id=order.order_id,
                    ticker=order.ticker, error=str(exc),
                )
                continue
            order.status = LiveOrderStatus.LIVE_CANCELLED
            order.cancelled_ts = now.isoformat()
            self.state.closed[intent_id] = order
            del self.state.resting[intent_id]
            cancelled.append(intent_id)
            log.info(
                "live_denylist_resting_cancelled",
                intent_id=intent_id, ticker=order.ticker, series=prefix,
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
                self._client.delete(f"/portfolio/events/orders/{order.order_id}")
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
        if outcome == -1:
            # Void: return to entry (zero payoff). We still net out the entry
            # fee Kalshi already charged on the fill (fee_cost_usd).
            payoff = 0.0
        else:
            # The bought contract pays $1 when the market resolves to ITS side,
            # else $0. outcome 1 == market resolved YES, 0 == NO. A NO order
            # (the v18 underdog arm) wins when outcome == 0.
            won = (order.side == "yes" and outcome == 1) or (
                order.side == "no" and outcome == 0
            )
            payoff = (1.0 - price) if won else -price
        # Subtract Kalshi's ACTUAL fees (captured per-fill in reconcile_fills),
        # not a modeled schedule. The old model (2x ceil(1.75*P*(1-P)),
        # series-blind) over-deducted ~3-4x vs reality, understating realized
        # P&L and biasing the rolling-30 edge kill toward tripping (verified
        # 2026-06-13 against /portfolio/fills fee_cost). Fees are charged once
        # at fill time; settlement is not a trade, so there is no exit fee.
        return payoff * order.filled_count - order.fee_cost_usd

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
