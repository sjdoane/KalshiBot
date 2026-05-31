"""v16 Gate A / Gate B evaluator (read-only).

Reads the shadow-logger output (data/v16/shadow/entries.parquet +
snapshots.parquet), fetches each fire ticker's Kalshi settlement, and reports
Gate A (does the lag exist) and Gate B (is it harvestable at executable prices)
with night-cluster and week-cluster bootstrap CIs, plus the season verdict per
research/v16/01-methodology-lock.md.

This is the ANALYSIS half of the study; it places no orders and makes only
read-only GET calls. Run it any time to see progress (it will say UNDERPOWERED
until ~120 nights are collected) and at season end for the binding verdict.

  .venv\\Scripts\\python.exe scripts\\v16\\evaluate_gates.py
  # or, on the venv v1 uses:
  uv run python scripts/v16/evaluate_gates.py

Settlement note: the logger does not capture settlement live (timing); this
evaluator fetches it at eval time via GET /markets/{ticker} (result yes/no),
cached to data/v16/shadow/settlements.json so repeat runs do not refetch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
sys.path.insert(0, str(BASE / "src"))

load_dotenv(BASE / ".env")

from kalshi_bot.analysis.lead_lag_gates import (  # noqa: E402
    clv_dollars,
    evaluate_gate,
    is_fillable_marketable,
    marketable_settlement_pnl,
    season_verdict,
)
from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient  # noqa: E402

SHADOW_DIR = BASE / "data" / "v16" / "shadow"
ENTRIES_PATH = SHADOW_DIR / "entries.parquet"
SNAPSHOTS_PATH = SHADOW_DIR / "snapshots.parquet"
SETTLEMENTS_PATH = SHADOW_DIR / "settlements.json"
REPORT_PATH = SHADOW_DIR / "gate_report.json"


def load_settlements() -> dict[str, int | None]:
    if not SETTLEMENTS_PATH.exists():
        return {}
    try:
        return json.loads(SETTLEMENTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_settlements(s: dict) -> None:
    SETTLEMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTLEMENTS_PATH.write_text(json.dumps(s, indent=2, default=str), encoding="utf-8")


def fetch_settlement(kc: KalshiClient, ticker: str) -> int | None:
    """Return 1 (resolved yes), 0 (resolved no), or None (unresolved/void).
    Kalshi terminal status is 'finalized'; result is 'yes'/'no'."""
    try:
        resp = kc.get(f"/markets/{ticker}")
    except Exception:  # noqa: BLE001
        return None
    market = resp.get("market", {}) or {}
    status = (market.get("status") or "").lower()
    if status not in ("finalized", "settled"):
        return None
    result = (market.get("result") or "").strip().lower()
    if result == "yes":
        return 1
    if result == "no":
        return 0
    return None  # void / scalar / unrecognized -> excluded from settlement EV


def close_yes_bid_by_fire(snapshots: pd.DataFrame) -> dict[tuple, float]:
    """Map (game_id, side, night_id) -> executable closing yes_bid, taking the
    'close' re-snapshot with a valid two-sided/parity book (book_status ok and a
    non-null yes_bid). Fires without a usable close leg are absent (excluded
    from Gate A)."""
    out: dict[tuple, float] = {}
    if snapshots.empty:
        return out
    close = snapshots[snapshots["snapshot_label"] == "close"]
    for _i, r in close.iterrows():
        if r.get("book_status") != "ok":
            continue
        yb = r.get("yes_bid")
        if yb is None or (isinstance(yb, float) and pd.isna(yb)):
            continue
        key = (r.get("game_id"), r.get("side"), r.get("night_id"))
        out.setdefault(key, float(yb))
    return out


def _f(v) -> float | None:
    if v is None:
        return None
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(fv) else fv


def main() -> int:
    if not ENTRIES_PATH.exists():
        print("No entries.parquet yet. Run the shadow logger first.")
        return 0
    entries = pd.read_parquet(ENTRIES_PATH)
    snapshots = pd.read_parquet(SNAPSHOTS_PATH) if SNAPSHOTS_PATH.exists() else pd.DataFrame()
    fires = entries[entries["fired"] == True]  # noqa: E712
    n_fires = len(fires)
    print(f"fires logged: {n_fires}")
    if n_fires == 0:
        print("No fires yet; nothing to evaluate.")
        return 0

    bs_counts = fires["book_status"].value_counts().to_dict() if "book_status" in fires else {}
    print(f"entry book_status: {bs_counts}")
    close_map = close_yes_bid_by_fire(snapshots)
    print(f"fires with a usable close leg: {len(close_map)}")

    settlements = load_settlements()
    settings = Settings()
    clv_vals: list[float | None] = []
    clv_nights: list = []
    clv_weeks: list = []
    b_vals: list[float | None] = []
    b_nights: list = []
    b_weeks: list = []
    n_fillable = 0
    n_settled = 0
    with KalshiClient(settings) as kc:
        for _i, e in fires.iterrows():
            ticker = e.get("ticker") or ""
            night = e.get("night_id")
            week = e.get("week_id")
            entry_yes_ask = _f(e.get("yes_ask"))
            target_implied = _f(e.get("target_implied"))
            no_depth = _f(e.get("no_depth"))  # depth backing the parity yes_ask
            key = (e.get("game_id"), e.get("side"), night)

            # Gate A: CLV to the executable closing price (needs a close leg).
            close_bid = close_map.get(key)
            clv = clv_dollars(entry_yes_ask, close_bid)
            clv_vals.append(clv)
            clv_nights.append(night)
            clv_weeks.append(week)

            # Gate B: marketable settlement EV over FILLABLE fires only.
            if not ticker:
                continue
            # Cache ONLY definitive results (0/1). A not-yet-settled market
            # returns None; do NOT cache that, or the market is never refetched
            # once it settles and the fire is dropped from Gate B forever.
            outcome = settlements.get(ticker)
            if outcome is None:
                outcome = fetch_settlement(kc, ticker)
                if outcome is not None:
                    settlements[ticker] = outcome
            if outcome is None:
                continue  # not yet settled / void: excluded from Gate B
            n_settled += 1
            if is_fillable_marketable(entry_yes_ask, target_implied, no_depth, size=1.0):
                n_fillable += 1
                b_vals.append(marketable_settlement_pnl(entry_yes_ask, outcome))
                b_nights.append(night)
                b_weeks.append(week)
    save_settlements(settlements)
    print(f"fires settled: {n_settled}; fillable (Gate B): {n_fillable}")

    gate_a = evaluate_gate("Gate A (CLV)", clv_vals, clv_nights, clv_weeks, rng_seed=0)
    gate_b = (
        evaluate_gate("Gate B (settlement EV)", b_vals, b_nights, b_weeks, rng_seed=0)
        if b_vals else None
    )
    code, rec = season_verdict(gate_a, gate_b)

    def _show(g) -> None:
        if g is None:
            print("  (no usable observations)")
            return
        print(
            f"  n={g.n_obs} nights={g.n_nights} mean=${g.mean:+.4f} "
            f"night95=[{g.night_ci_lower:+.4f}, {g.night_ci_upper:+.4f}] "
            f"week95=[{g.week_ci_lower:+.4f}, {g.week_ci_upper:+.4f}] "
            f"passed={g.passed}"
        )

    print("\nGate A (lag exists; CLV to closing executable price):")
    _show(gate_a)
    print("Gate B (harvestable; marketable-stale-ask settlement EV):")
    _show(gate_b)
    print(f"\nVERDICT: {code}\n  {rec}")

    report = {
        "n_fires": int(n_fires), "n_close_leg": len(close_map),
        "n_settled": n_settled, "n_fillable": n_fillable,
        "entry_book_status": bs_counts,
        "gate_a": None if gate_a is None else gate_a.__dict__,
        "gate_b": None if gate_b is None else gate_b.__dict__,
        "verdict": code, "recommendation": rec,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
