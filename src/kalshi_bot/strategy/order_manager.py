"""Order manager: paper or live mode for maker-quote bot.

PAPER mode:
- Posts no orders to Kalshi.
- Records simulated orders in a JSON state file.
- Reconciles "fills" by checking subsequent trades on the same market;
  if any taker trade in the market matches or crosses our paper-bid
  price, mark as filled at our bid price.
- Computes realized P&L per filled order.

LIVE mode (NOT yet implemented; placeholder):
- Posts real maker orders via Kalshi /portfolio/orders endpoint.
- Reconciles via /portfolio/fills.
- Requires WRITE-scope API key.

Persistence: JSON file at `data/paper_trades/state.json`. Loaded on
each call. Atomic writes via tempfile + rename.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class OrderStatus(Enum):
    PAPER_PENDING = "paper_pending"
    PAPER_FILLED = "paper_filled"
    PAPER_CANCELLED = "paper_cancelled"
    PAPER_EXPIRED = "paper_expired"
    LIVE_PENDING = "live_pending"  # placeholder for future
    LIVE_FILLED = "live_filled"
    LIVE_CANCELLED = "live_cancelled"


@dataclass
class PaperOrder:
    order_id: str
    ticker: str
    series_ticker: str
    event_ticker: str
    side: str  # "yes" or "no"
    target_price: float  # in dollars
    contracts: int
    expected_net_edge: float
    recalibrated_prob: float
    market_mid_at_placement: float
    placed_ts: str  # ISO datetime
    status: OrderStatus = OrderStatus.PAPER_PENDING
    filled_ts: str | None = None
    filled_price: float | None = None
    resolution_ts: str | None = None
    resolution_outcome: int | None = None  # 0 or 1 (YES = 1)
    realized_pnl_usd: float | None = None


@dataclass
class PaperState:
    open_orders: dict[str, PaperOrder] = field(default_factory=dict)
    filled_orders: dict[str, PaperOrder] = field(default_factory=dict)
    closed_orders: dict[str, PaperOrder] = field(default_factory=dict)
    starting_bankroll_usd: float = 25.0
    realized_pnl_total_usd: float = 0.0
    placement_attempts_total: int = 0
    last_updated_ts: str = ""


class PaperOrderManager:
    """Manage paper-trading state on disk.

    Concurrency: not thread-safe. Designed for single-process invocation
    via a periodic scheduler. The state.json file is locked by
    filesystem semantics; concurrent writers can corrupt it. Operator
    should run only ONE paper-trade process at a time.
    """

    def __init__(self, state_path: Path | None = None) -> None:
        self.state_path = state_path or Path("data/paper_trades/state.json")
        self.state = self._load()

    def _load(self) -> PaperState:
        if not self.state_path.exists():
            return PaperState()
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.error("paper_state_corrupted", error=str(exc), path=str(self.state_path))
            raise
        def _to_orders(d: dict) -> dict[str, PaperOrder]:
            return {
                oid: PaperOrder(**{**v, "status": OrderStatus(v["status"])})
                for oid, v in d.items()
            }
        return PaperState(
            open_orders=_to_orders(raw.get("open_orders", {})),
            filled_orders=_to_orders(raw.get("filled_orders", {})),
            closed_orders=_to_orders(raw.get("closed_orders", {})),
            starting_bankroll_usd=raw.get("starting_bankroll_usd", 25.0),
            realized_pnl_total_usd=raw.get("realized_pnl_total_usd", 0.0),
            placement_attempts_total=raw.get("placement_attempts_total", 0),
            last_updated_ts=raw.get("last_updated_ts", ""),
        )

    def _save(self) -> None:
        def _orders_to_dict(d: dict[str, PaperOrder]) -> dict[str, dict]:
            return {oid: {**asdict(o), "status": o.status.value} for oid, o in d.items()}
        payload = {
            "open_orders": _orders_to_dict(self.state.open_orders),
            "filled_orders": _orders_to_dict(self.state.filled_orders),
            "closed_orders": _orders_to_dict(self.state.closed_orders),
            "starting_bankroll_usd": self.state.starting_bankroll_usd,
            "realized_pnl_total_usd": self.state.realized_pnl_total_usd,
            "placement_attempts_total": self.state.placement_attempts_total,
            "last_updated_ts": datetime.now(UTC).isoformat(),
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.state_path)

    def place_paper_order(
        self,
        *,
        ticker: str,
        series_ticker: str,
        event_ticker: str,
        side: str,
        target_price: float,
        contracts: int,
        expected_net_edge: float,
        recalibrated_prob: float,
        market_mid_at_placement: float,
    ) -> PaperOrder:
        """Record a new simulated maker order."""
        ts = datetime.now(UTC).isoformat()
        order_id = f"paper-{ticker}-{ts}"
        order = PaperOrder(
            order_id=order_id,
            ticker=ticker,
            series_ticker=series_ticker,
            event_ticker=event_ticker,
            side=side,
            target_price=target_price,
            contracts=contracts,
            expected_net_edge=expected_net_edge,
            recalibrated_prob=recalibrated_prob,
            market_mid_at_placement=market_mid_at_placement,
            placed_ts=ts,
        )
        self.state.open_orders[order_id] = order
        self.state.placement_attempts_total += 1
        self._save()
        log.info("paper_order_placed",
                 order_id=order_id, ticker=ticker, side=side,
                 target_price=target_price, contracts=contracts,
                 expected_net_edge=expected_net_edge)
        return order

    def reconcile_fills(
        self,
        ticker: str,
        recent_trades: list[dict[str, Any]],
    ) -> list[PaperOrder]:
        """Check if any open orders for this ticker can be marked filled.

        recent_trades: list of dicts with at least 'yes_price', 'taker_side',
        'created_time'. From Kalshi /markets/trades endpoint.

        Fill rule (PAPER mode): if a taker trade exists at or beyond our
        bid price, mark our order filled at OUR bid price.
        - For side=yes (we bid YES): any taker sell at <= target_price
        - For side=no (we sell YES = buy NO): any taker buy at >= target_price

        This is a charitable fill simulation that OVERESTIMATES fill rate
        vs reality (institutional MMs would step inside). Document this
        in the runbook.
        """
        filled: list[PaperOrder] = []
        for order_id, order in list(self.state.open_orders.items()):
            if order.ticker != ticker:
                continue
            for t in recent_trades:
                price_str = t.get("yes_price_dollars") or t.get("yes_price")
                if price_str is None:
                    continue
                try:
                    price = float(price_str) if isinstance(price_str, str) else float(price_str) / 100.0
                except (TypeError, ValueError):
                    continue
                taker_side = (t.get("taker_side") or "").lower()
                # YES taker buys (lifts asks) at higher prices; YES taker
                # sells (hits bids) at lower prices. A taker SELL at our
                # bid price means our resting bid got hit -> we filled.
                if order.side == "yes" and taker_side == "no" and price <= order.target_price:
                    filled.append(self._mark_filled(order_id, price=order.target_price, ts=t.get("created_time", "")))
                    break
                if order.side == "no" and taker_side == "yes" and price >= order.target_price:
                    filled.append(self._mark_filled(order_id, price=order.target_price, ts=t.get("created_time", "")))
                    break
        if filled:
            self._save()
        return filled

    def _mark_filled(self, order_id: str, *, price: float, ts: str) -> PaperOrder:
        order = self.state.open_orders.pop(order_id)
        order.status = OrderStatus.PAPER_FILLED
        order.filled_ts = ts
        order.filled_price = price
        self.state.filled_orders[order_id] = order
        log.info("paper_order_filled", order_id=order_id, price=price)
        return order

    def settle_at_resolution(
        self,
        ticker: str,
        outcome: int,
        resolution_ts: str,
    ) -> list[PaperOrder]:
        """Settle all filled orders for a market that just resolved."""
        settled: list[PaperOrder] = []
        for order_id, order in list(self.state.filled_orders.items()):
            if order.ticker != ticker:
                continue
            order.resolution_ts = resolution_ts
            order.resolution_outcome = outcome
            if order.side == "yes":
                payoff = (1.0 if outcome == 1 else 0.0) - order.filled_price
            else:
                payoff = (1.0 if outcome == 0 else 0.0) - (1.0 - order.filled_price)
            # Subtract round-trip maker fee per the methodology lock
            # (2x single-side). Kalshi settlement is actually fee-free, so
            # buy-to-hold-to-settle realistically only pays the entry fee.
            # The methodology uses round-trip as a conservative
            # approximation. Realized P&L here matches the methodology
            # model and will systematically UNDERSHOOT a real bot's
            # actual P&L by one maker fee per contract.
            from kalshi_bot.analysis.metrics import kalshi_maker_fee_per_contract
            fee = 2.0 * kalshi_maker_fee_per_contract(order.filled_price)
            pnl_per_contract = payoff - fee
            order.realized_pnl_usd = pnl_per_contract * order.contracts
            order.status = OrderStatus.PAPER_FILLED  # remains filled status; closed_orders tracks settled
            self.state.closed_orders[order_id] = order
            del self.state.filled_orders[order_id]
            self.state.realized_pnl_total_usd += order.realized_pnl_usd
            settled.append(order)
            log.info("paper_order_settled",
                     order_id=order_id, ticker=ticker, outcome=outcome,
                     pnl_usd=order.realized_pnl_usd)
        if settled:
            self._save()
        return settled

    def current_paper_bankroll(self) -> float:
        return self.state.starting_bankroll_usd + self.state.realized_pnl_total_usd
