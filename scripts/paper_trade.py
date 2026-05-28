"""Phase 3 paper-trading entry point.

Loops:
1. Scan open Kalshi markets in the configured category, filter by
   methodology criteria.
2. For each candidate: fetch recent trades, compute current one-sided
   flow + small-trade VWAP, recalibrate via the trained isotonic model,
   compute expected net edge, decide whether to quote.
3. Place paper orders (no live capital).
4. Reconcile fills against subsequent taker trade tape.
5. Settle orders for markets that resolved since last loop.
6. Update drawdown monitor; honor pause / halt actions.
7. Discord-alert on fills + drawdown events.

Cadence: configurable; default every 15 minutes for low-frequency
politics or sports futures.

CALLING CONVENTION:
    uv run python -m scripts.paper_trade \
        --category Politics \
        --calibrator data/processed/politics_phase2_dataset.parquet \
        --min-lifetime-days 30 \
        --cadence 900 \
        --max-concurrent 5 \
        --contracts-per-fill 3

LIVE mode is intentionally NOT implemented; only paper. To enable live:
1. Phase 2/Sports gate must PASS
2. Operator wake-up authorization required
3. Implement Kalshi /portfolio/orders integration in this script
4. Acquire Kalshi WRITE-scope API key
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import structlog

from kalshi_bot.alerts.discord import post as send_discord
from kalshi_bot.analysis.calibration import IsotonicCalibrator
from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.logging import configure_logging
from kalshi_bot.risk.drawdown import DrawdownAction, DrawdownMonitor
from kalshi_bot.strategy.market_scanner import ScannerConfig, scan
from kalshi_bot.strategy.order_manager import PaperOrderManager
from kalshi_bot.strategy.pricing import decide, isotonic_recalibrate

log = structlog.get_logger(__name__)


def fit_calibrator_from_dataset(dataset_path: Path) -> IsotonicCalibrator:
    """Fit isotonic on the full historical dataset (no train/test split).

    Phase 3 uses the entire validated dataset as 'training data' for the
    live model; the gate already validated OOS performance.
    """
    df = pd.read_parquet(dataset_path)
    return IsotonicCalibrator().fit(df["mid_price_at_T_small"], df["outcome"])


def one_loop(
    client: KalshiClient,
    calibrator: IsotonicCalibrator,
    scanner_cfg: ScannerConfig,
    om: PaperOrderManager,
    dd: DrawdownMonitor,
    *,
    contracts_per_fill: int,
    max_concurrent: int,
    min_net_edge: float = 0.01,
    discord_url: str | None = None,
) -> None:
    """One scan + price + place + reconcile cycle."""
    # 0. Update drawdown monitor with current paper bankroll
    bankroll = om.current_paper_bankroll()
    dd_action = dd.update(bankroll)
    if dd_action == DrawdownAction.HALT:
        log.error("drawdown_halt", bankroll=bankroll)
        if discord_url:
            send_discord(discord_url, content=f"HALT: drawdown at {dd.state.current_drawdown_pct*100:.1f}%")
        return
    if not dd.allowed_to_place_orders():
        log.warning("paused_for_drawdown", action=dd_action.value)
        return

    # 1. Scan candidates
    candidates = scan(client, scanner_cfg)
    if not candidates:
        log.info("no_candidates_this_loop")
        return

    # 2. Reconcile fills + settle resolved markets BEFORE placing new orders
    for _raw_market, snap in candidates:
        # Pull recent trades for this market to reconcile any open orders
        try:
            recent = list(client.paginate(
                "/markets/trades", item_key="trades", limit=100,
                ticker=snap.ticker, max_pages=2,
            ))
        except Exception as exc:
            log.warning("trades_fetch_failed", ticker=snap.ticker, error=str(exc))
            continue
        filled = om.reconcile_fills(snap.ticker, recent)
        for f in filled:
            if discord_url:
                send_discord(
                    discord_url,
                    content=f"PAPER FILL {f.ticker} {f.side} {f.contracts}@{f.filled_price:.4f} "
                            f"net_edge={f.expected_net_edge*100:.2f}pp",
                )

    # 3. Price and place orders for top candidates
    n_open = len(om.state.open_orders)
    slots_left = max(0, max_concurrent - n_open)
    if slots_left <= 0:
        log.info("max_concurrent_reached", n_open=n_open)
        return

    # Compute expected edge per candidate, rank, take top K
    scored: list = []
    for _raw_market, snap in candidates:
        mid = (snap.yes_bid + snap.yes_ask) / 2.0
        recal = isotonic_recalibrate(mid, calibrator)
        decision = decide(snap, recal, min_net_edge=min_net_edge)
        if decision is not None:
            scored.append((decision.expected_net_edge, snap, decision))
    scored.sort(key=lambda x: -x[0])

    sized = max(1, int(contracts_per_fill * dd.position_size_multiplier()))
    n_placed = 0
    for _edge, snap, decision in scored[:slots_left]:
        # Avoid duplicate orders on the same ticker
        existing = any(o.ticker == snap.ticker for o in om.state.open_orders.values())
        if existing:
            continue
        order = om.place_paper_order(
            ticker=snap.ticker,
            series_ticker=snap.series_ticker,
            event_ticker=snap.event_ticker,
            side=decision.side,
            target_price=decision.target_price,
            contracts=sized,
            expected_net_edge=decision.expected_net_edge,
            recalibrated_prob=decision.recalibrated_prob,
            market_mid_at_placement=decision.market_mid,
        )
        n_placed += 1
        log.info("paper_order_placed_in_loop",
                 ticker=order.ticker, side=order.side,
                 target_price=order.target_price, contracts=order.contracts,
                 expected_net_edge=order.expected_net_edge)
    if n_placed > 0 and discord_url:
        send_discord(
            discord_url,
            content=f"PAPER PLACED {n_placed} order(s). Bankroll: ${bankroll:.2f}. "
                    f"DD: {dd.state.current_drawdown_pct*100:.1f}%",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", required=True, choices=["Politics", "Sports"],
                        help="Kalshi category to scan.")
    parser.add_argument("--calibrator", type=Path, required=True,
                        help="Path to dataset parquet used to fit isotonic.")
    parser.add_argument("--min-lifetime-days", type=int, required=True,
                        help="Long-horizon filter (30 for Sports, 30 for Politics x H).")
    parser.add_argument("--cadence", type=int, default=900,
                        help="Seconds between loops. Default 900 = 15 minutes.")
    parser.add_argument("--max-concurrent", type=int, default=5)
    parser.add_argument("--contracts-per-fill", type=int, default=3)
    parser.add_argument("--min-net-edge", type=float, default=0.01,
                        help="Minimum net edge per contract to place a paper order.")
    parser.add_argument("--starting-bankroll", type=float, default=25.0)
    parser.add_argument("--once", action="store_true",
                        help="Run a single loop and exit (for testing).")
    args = parser.parse_args()

    configure_logging()
    log = structlog.get_logger("paper_trade")
    settings = load_settings()
    discord_url = settings.DISCORD_WEBHOOK_URL or None

    if not args.calibrator.exists():
        log.error("calibrator_dataset_missing", path=str(args.calibrator))
        return 1
    cal = fit_calibrator_from_dataset(args.calibrator)
    log.info("calibrator_fitted", dataset=str(args.calibrator))

    om = PaperOrderManager()
    if om.state.starting_bankroll_usd != args.starting_bankroll:
        om.state.starting_bankroll_usd = args.starting_bankroll
    dd = DrawdownMonitor(starting_bankroll_usd=om.current_paper_bankroll())

    scanner_cfg = ScannerConfig(category=args.category, min_lifetime_days=args.min_lifetime_days)

    if args.once:
        with KalshiClient(settings) as client:
            one_loop(client, cal, scanner_cfg, om, dd,
                     contracts_per_fill=args.contracts_per_fill,
                     max_concurrent=args.max_concurrent,
                     min_net_edge=args.min_net_edge, discord_url=discord_url)
        return 0

    if discord_url:
        send_discord(discord_url, content=f"PAPER TRADE STARTED category={args.category} cadence={args.cadence}s")

    with KalshiClient(settings) as client:
        while True:
            try:
                one_loop(client, cal, scanner_cfg, om, dd,
                         contracts_per_fill=args.contracts_per_fill,
                         max_concurrent=args.max_concurrent,
                         min_net_edge=args.min_net_edge, discord_url=discord_url)
            except Exception as exc:
                log.error("loop_failed", error=str(exc))
                if discord_url:
                    send_discord(discord_url, content=f"PAPER TRADE LOOP FAILED: {exc!s}")
            time.sleep(args.cadence)

    return 0


if __name__ == "__main__":
    sys.exit(main())
