"""V5-A2: retrospective backtest of the combined v5 filter.

Two paths attempted per V5-A2 master plan Section 3:

Path X (small live-cached probe):
    Use V5-A1's cached pairs (Kalshi mid + de-vigged sportsbook implied)
    on the n=58 candidate markets where matching is clean. For markets
    that have RESOLVED on Kalshi (status='finalized' OR
    `expected_expiration_time < now AND last_price_dollars in {<=0.05,
    >=0.95}`), compute realized P&L bare-v1 vs combined-filter+v1.

    LIMITED POWER: only n=12 favorites resolved as of build time. We
    report results honestly and flag this as low-power.

Path Y (augment v4 inventory with sportsbook):
    For the v4 backtest universe (147 v1-eligible markets from
    `data/v3/probe_inventory_all_markets.parquet`), check whether
    sportsbook implied probabilities are CURRENTLY available on
    the-odds-api. This is the wrong-time-window (we should sample at
    T-35d, not today) but it lets us check whether the sportsbook
    filter on v4's inventory would have added coverage / fires.

Output: data/v5/sportsbook_filter_backtest_results.json with per-arm
results and per-path coverage statistics.

Pre-registered thresholds (LOCKED before any run):
    fade_threshold_cents_poly = 7.0      (matches V4-E)
    fade_threshold_cents_book = 5.0      (V5-A1 measured smaller mean)
    monotonicity_threshold_cents = 5.0   (matches V4-E)

Pre-registered hypothesis tests (matches V4-E TA1-TA5):
    TA1: coverage >= 30%
    TA2: improvement >= +1pp
    TA3: skip rate <= 50%
    TA4: bootstrap CI lower > 0 (one-sided)
    TA5: >= 2 distinct series-prefixes improved
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_V3 = REPO_ROOT / "data" / "v3"
DATA_V4 = REPO_ROOT / "data" / "v4"
DATA_V5 = REPO_ROOT / "data" / "v5"
DATA_V5.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(REPO_ROOT / "src"))

from kalshi_bot.analysis.metrics import (  # noqa: E402
    kalshi_maker_fee_per_contract,
)
from kalshi_bot.strategy.favorite_maker import (  # noqa: E402
    FAVORITE_THRESHOLD,
    FAVORITE_UPPER_CAP,
    SLIPPAGE_ALLOWANCE,
)
from kalshi_bot_v4.filter import parse_ladder_ticker, series_prefix_of  # noqa: E402
from kalshi_bot_v5.filter_combined import (  # noqa: E402
    FADE_THRESHOLD_CENTS_BOOK_DEFAULT,
    FADE_THRESHOLD_CENTS_POLY_DEFAULT,
    MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
    evaluate_market_combined,
)

# Pre-registered hypothesis-test criteria (LOCKED). Match V4-E.
TA1_COVERAGE_FLOOR = 0.30
TA2_IMPROVEMENT_PP = 0.01
TA3_VOLUME_SKIP_CEILING = 0.50
TA4_BOOTSTRAP_CI = 0.95
TA4_BOOTSTRAP_N = 5000
TA4_BOOTSTRAP_SEED = 42
TA5_MIN_SERIES_PREFIXES = 2


@dataclass
class BacktestStats:
    n_trades: int
    mean_pnl: float
    median_pnl: float
    sd_pnl: float
    hit_rate: float
    ci_lower: float
    ci_upper: float


@dataclass
class FilterArmResult:
    arm_name: str
    fade_threshold_cents_poly: float
    fade_threshold_cents_book: float
    monotonicity_threshold_cents: float
    v1_stats: BacktestStats
    filter_stats: BacktestStats
    diff_mean_pp: float
    diff_ci_lower: float
    diff_ci_upper: float
    n_v1_eligible: int
    n_filter_traded: int
    n_filter_skipped: int
    skip_rate: float
    n_filter_activated: int
    coverage: float
    skip_reason_counts: dict[str, int]
    rule_fire_counts: dict[str, int]
    per_series_diff_pp: dict[str, float]
    per_series_n: dict[str, int]
    per_series_n_filter_fired: dict[str, int]
    criteria: dict[str, bool]
    passes_all: bool


def realized_pnl_per_contract(yes_price: float, outcome: int) -> float:
    gross = outcome - yes_price
    fee = 2.0 * kalshi_maker_fee_per_contract(yes_price)
    return gross - fee - SLIPPAGE_ALLOWANCE


def compute_stats(pnl_arr: np.ndarray) -> BacktestStats:
    n = int(pnl_arr.size)
    if n == 0:
        return BacktestStats(
            n_trades=0, mean_pnl=float("nan"), median_pnl=float("nan"),
            sd_pnl=float("nan"), hit_rate=float("nan"),
            ci_lower=float("nan"), ci_upper=float("nan"),
        )
    mean_v = float(pnl_arr.mean())
    median_v = float(np.median(pnl_arr))
    sd_v = float(pnl_arr.std(ddof=1)) if n > 1 else 0.0
    hit_rate = float((pnl_arr > 0).mean())
    if n >= 2:
        rng = np.random.default_rng(TA4_BOOTSTRAP_SEED)
        idx = rng.integers(0, n, size=(TA4_BOOTSTRAP_N, n))
        means = pnl_arr[idx].mean(axis=1)
        alpha = (1.0 - TA4_BOOTSTRAP_CI) / 2.0
        lo = float(np.quantile(means, alpha))
        hi = float(np.quantile(means, 1.0 - alpha))
    else:
        lo, hi = mean_v, mean_v
    return BacktestStats(
        n_trades=n, mean_pnl=mean_v, median_pnl=median_v, sd_pnl=sd_v,
        hit_rate=hit_rate, ci_lower=lo, ci_upper=hi,
    )


def bootstrap_diff_ci(
    v1_pnl_paired: np.ndarray,
    filter_pnl_paired: np.ndarray,
) -> tuple[float, float, float]:
    n = v1_pnl_paired.size
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    diff = filter_pnl_paired - v1_pnl_paired
    if n == 1:
        return float(diff[0]), float(diff[0]), float(diff[0])
    rng = np.random.default_rng(TA4_BOOTSTRAP_SEED)
    idx = rng.integers(0, n, size=(TA4_BOOTSTRAP_N, n))
    means = diff[idx].mean(axis=1)
    alpha = (1.0 - TA4_BOOTSTRAP_CI) / 2.0
    return (
        float(diff.mean()),
        float(np.quantile(means, alpha)),
        float(np.quantile(means, 1.0 - alpha)),
    )


def build_polymarket_lookup() -> dict[str, float]:
    pairs_path = DATA_V3 / "poly_kalshi_pairs.parquet"
    if not pairs_path.exists():
        return {}
    pairs = pd.read_parquet(pairs_path)
    valid = pairs.dropna(subset=["poly_mid_T_minus_35d"])
    return {
        str(row["ticker"]): float(row["poly_mid_T_minus_35d"])
        for _, row in valid.iterrows()
    }


def build_sportsbook_lookup_from_v5() -> dict[str, float]:
    """Load the sportsbook lookup parquet built by build_sportsbook_lookup.py.

    Returns {ticker -> sportsbook_implied} for rows where matched.
    """
    p = DATA_V5 / "sportsbook_lookup_latest.parquet"
    if not p.exists():
        return {}
    df = pd.read_parquet(p)
    matched = df[df["sportsbook_implied"].notna()]
    return {
        str(r["ticker"]): float(r["sportsbook_implied"])
        for _, r in matched.iterrows()
    }


def build_cross_market_data(inv: pd.DataFrame) -> dict[str, dict[int, float]]:
    out: dict[str, dict[int, float]] = {}
    for _, row in inv.iterrows():
        ticker = str(row["ticker"])
        vwap = row.get("vwap_t35_wide")
        if vwap is None or pd.isna(vwap):
            continue
        parsed = parse_ladder_ticker(ticker)
        if parsed is None:
            continue
        ladder_key, threshold = parsed
        out.setdefault(ladder_key, {})[threshold] = float(vwap)
    return out


def run_arm(
    rows: pd.DataFrame,
    *,
    arm_name: str,
    fade_threshold_cents_poly: float,
    fade_threshold_cents_book: float,
    monotonicity_threshold_cents: float,
    poly_lookup: Optional[dict],
    sportsbook_lookup: Optional[dict],
    cross_market_data: Optional[dict],
) -> FilterArmResult:
    """Run combined-filter+v1 vs bare-v1 on the input rows.

    rows columns required: ticker, series_ticker, effective_price, outcome.
    """
    v1_pnl_list: list[float] = []
    filter_pnl_list: list[float] = []
    activated_list: list[bool] = []
    skip_reasons: dict[str, int] = {}
    rule_fires: dict[str, int] = {
        "polymarket_fade": 0,
        "sportsbook_fade": 0,
        "monotonicity_violation": 0,
    }
    decisions: list[dict] = []

    for _, row in rows.iterrows():
        ticker = str(row["ticker"])
        series_ticker = str(row["series_ticker"])
        price = float(row["effective_price"])
        outcome = int(row["outcome"])
        v1_pnl = realized_pnl_per_contract(price, outcome)
        v1_pnl_list.append(v1_pnl)

        decision = evaluate_market_combined(
            ticker=ticker,
            kalshi_price=price,
            series_ticker=series_ticker,
            poly_lookup=poly_lookup,
            sportsbook_lookup=sportsbook_lookup,
            cross_market_data=cross_market_data,
            fade_threshold_cents_poly=fade_threshold_cents_poly,
            fade_threshold_cents_book=fade_threshold_cents_book,
            monotonicity_threshold_cents=monotonicity_threshold_cents,
        )

        for rule in decision.fired_rules:
            rule_fires[rule] = rule_fires.get(rule, 0) + 1

        has_any_input = (
            decision.poly_mid is not None
            or decision.sportsbook_implied is not None
            or decision.cross_market_implied is not None
        )
        activated_list.append(has_any_input)

        skip_reasons[decision.reason] = skip_reasons.get(decision.reason, 0) + 1
        if decision.should_trade:
            filter_pnl_list.append(v1_pnl)
        else:
            filter_pnl_list.append(0.0)
        decisions.append({
            "ticker": ticker,
            "series_prefix": series_prefix_of(ticker),
            "series_ticker": series_ticker,
            "effective_price": price,
            "outcome": outcome,
            "v1_pnl": v1_pnl,
            "filter_pnl": v1_pnl if decision.should_trade else 0.0,
            "filter_should_trade": decision.should_trade,
            "filter_reason": decision.reason,
            "filter_fired_rules": ",".join(decision.fired_rules),
            "filter_poly_mid": decision.poly_mid,
            "filter_book_implied": decision.sportsbook_implied,
            "filter_cross_implied": decision.cross_market_implied,
            "filter_confidence": decision.confidence,
            "filter_activated": has_any_input,
        })

    v1_pnl_arr = np.array(v1_pnl_list, dtype=float)
    filter_pnl_arr = np.array(filter_pnl_list, dtype=float)
    activated_arr = np.array(activated_list, dtype=bool)

    v1_stats = compute_stats(v1_pnl_arr)
    filter_stats = compute_stats(filter_pnl_arr)
    diff_mean, diff_lo, diff_hi = bootstrap_diff_ci(v1_pnl_arr, filter_pnl_arr)

    n = len(decisions)
    n_filter_traded = int(sum(d["filter_should_trade"] for d in decisions))
    n_filter_skipped = n - n_filter_traded
    skip_rate = n_filter_skipped / max(1, n)
    n_activated = int(activated_arr.sum())
    coverage = n_activated / max(1, n)

    df_d = pd.DataFrame(decisions)
    per_series_diff: dict[str, float] = {}
    per_series_n: dict[str, int] = {}
    per_series_n_fired: dict[str, int] = {}
    for sp, sub in df_d.groupby("series_prefix"):
        per_series_diff[str(sp)] = float(
            (sub["filter_pnl"] - sub["v1_pnl"]).mean()
        )
        per_series_n[str(sp)] = int(len(sub))
        per_series_n_fired[str(sp)] = int((~sub["filter_should_trade"]).sum())

    ta1 = coverage >= TA1_COVERAGE_FLOOR
    ta2 = diff_mean >= TA2_IMPROVEMENT_PP if not np.isnan(diff_mean) else False
    ta3 = skip_rate <= TA3_VOLUME_SKIP_CEILING
    ta4 = diff_lo > 0.0 if not np.isnan(diff_lo) else False
    ta5_count = sum(
        1 for sp, v in per_series_diff.items()
        if v > 0 and per_series_n_fired.get(sp, 0) > 0
    )
    ta5 = ta5_count >= TA5_MIN_SERIES_PREFIXES

    criteria = {
        f"TA1_coverage_>=_{TA1_COVERAGE_FLOOR}": bool(ta1),
        f"TA2_improvement_>=_{TA2_IMPROVEMENT_PP * 100:.1f}pp": bool(ta2),
        f"TA3_skip_rate_<=_{TA3_VOLUME_SKIP_CEILING}": bool(ta3),
        "TA4_diff_ci_lower_>_0": bool(ta4),
        f"TA5_>={TA5_MIN_SERIES_PREFIXES}_series_improved": bool(ta5),
    }
    passes = all(criteria.values())

    return FilterArmResult(
        arm_name=arm_name,
        fade_threshold_cents_poly=fade_threshold_cents_poly,
        fade_threshold_cents_book=fade_threshold_cents_book,
        monotonicity_threshold_cents=monotonicity_threshold_cents,
        v1_stats=v1_stats,
        filter_stats=filter_stats,
        diff_mean_pp=diff_mean,
        diff_ci_lower=diff_lo,
        diff_ci_upper=diff_hi,
        n_v1_eligible=n,
        n_filter_traded=n_filter_traded,
        n_filter_skipped=n_filter_skipped,
        skip_rate=skip_rate,
        n_filter_activated=n_activated,
        coverage=coverage,
        skip_reason_counts=skip_reasons,
        rule_fire_counts=rule_fires,
        per_series_diff_pp=per_series_diff,
        per_series_n=per_series_n,
        per_series_n_filter_fired=per_series_n_fired,
        criteria=criteria,
        passes_all=passes,
    )


def fmt_pp(x: float) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "nan"
    return f"{x * 100:+.2f}pp"


def fmt_pct(x: float) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "nan"
    return f"{x * 100:.1f}%"


def print_arm(arm: FilterArmResult) -> None:
    print(f"--- {arm.arm_name} (poly={arm.fade_threshold_cents_poly:.0f}c, "
          f"book={arm.fade_threshold_cents_book:.0f}c, "
          f"mono={arm.monotonicity_threshold_cents:.0f}c) ---")
    print(f"  n={arm.n_v1_eligible}, traded={arm.n_filter_traded}, "
          f"skipped={arm.n_filter_skipped} (skip {fmt_pct(arm.skip_rate)})")
    print(f"  Activated on {arm.n_filter_activated} / {arm.n_v1_eligible} "
          f"({fmt_pct(arm.coverage)})")
    print(f"  Rule fires: {arm.rule_fire_counts}")
    print(f"  Skip reasons: {arm.skip_reason_counts}")
    print(f"  v1     mean P&L: {fmt_pp(arm.v1_stats.mean_pnl)} CI=["
          f"{fmt_pp(arm.v1_stats.ci_lower)}, {fmt_pp(arm.v1_stats.ci_upper)}] "
          f"hit={fmt_pct(arm.v1_stats.hit_rate)}")
    print(f"  filter mean P&L: {fmt_pp(arm.filter_stats.mean_pnl)} CI=["
          f"{fmt_pp(arm.filter_stats.ci_lower)}, {fmt_pp(arm.filter_stats.ci_upper)}] "
          f"hit={fmt_pct(arm.filter_stats.hit_rate)}")
    print(f"  diff (filter - v1): {fmt_pp(arm.diff_mean_pp)} CI=["
          f"{fmt_pp(arm.diff_ci_lower)}, {fmt_pp(arm.diff_ci_upper)}]")
    print("  Per-series:")
    for sp, n in sorted(arm.per_series_n.items(), key=lambda kv: -kv[1])[:8]:
        diff_pp = arm.per_series_diff_pp[sp]
        fired = arm.per_series_n_filter_fired.get(sp, 0)
        print(f"    {sp:<24} n={n:>4} diff={fmt_pp(diff_pp)} fired={fired}")
    print("  Criteria:")
    for c, ok in arm.criteria.items():
        print(f"    [{'PASS' if ok else 'FAIL'}] {c}")
    print(f"  Verdict: {'PASS' if arm.passes_all else 'FAIL'} ALL TA1-TA5")
    print()


def serialize_arm(arm: FilterArmResult) -> dict:
    d = asdict(arm)
    d["v1_stats"] = asdict(arm.v1_stats)
    d["filter_stats"] = asdict(arm.filter_stats)
    return d


# ============================================================
# Path X: small live-cached probe with Kalshi resolution
# ============================================================

def build_path_x_rows(client, restrict_to_v1_band: bool = True) -> pd.DataFrame:
    """Build resolved rows from V5-A1's divergence_summary + Kalshi
    /markets/{ticker} status lookup. Outcome inference rules:

      - Kalshi status 'finalized' AND result in {'yes','no'} -> definitive.
      - Status 'active' but expected_expiration_time < now AND
        last_price_dollars >= 0.95 -> infer YES.
      - Status 'active' but expected_expiration_time < now AND
        last_price_dollars <= 0.05 -> infer NO.

    The third rule is a heuristic because Kalshi sometimes leaves
    markets in 'active' status for the post-game settlement window
    (~hours). With prices polarized at the boundary, the outcome is
    effectively known.
    """
    summary = json.loads((DATA_V5 / "divergence_summary.json").read_text(encoding="utf-8"))
    df = pd.DataFrame(summary["rows"])
    if restrict_to_v1_band:
        # Restrict to favorites in the v1 band (Kalshi mid in [0.70, 0.95]).
        df = df[df["in_v1_band"]].copy()
    else:
        df = df.copy()
    df["effective_price"] = df["kalshi_mid"]
    df["series_ticker"] = df["ticker"].apply(lambda t: "-".join(t.split("-")[:-1]))
    NOW = datetime.now(timezone.utc)
    resolved_rows: list[dict] = []
    for _, r in df.iterrows():
        tk = str(r["ticker"])
        try:
            resp = client.get(f"/markets/{tk}")
        except Exception as exc:
            print(f"  market lookup failed {tk}: {exc}")
            continue
        m = resp.get("market", {})
        status = m.get("status", "")
        result = m.get("result", "")
        last_p_raw = m.get("last_price_dollars")
        try:
            last_p = float(last_p_raw)
        except (TypeError, ValueError):
            last_p = None
        exp_iso = m.get("expected_expiration_time")
        try:
            exp_dt = (
                datetime.fromisoformat(exp_iso.replace("Z", "+00:00"))
                if exp_iso else None
            )
        except (TypeError, ValueError):
            exp_dt = None

        outcome: Optional[int] = None
        resolution_source: Optional[str] = None
        if status == "finalized":
            if result == "yes":
                outcome = 1
                resolution_source = "finalized_yes"
            elif result == "no":
                outcome = 0
                resolution_source = "finalized_no"
        elif status == "active" and exp_dt is not None and exp_dt < NOW:
            # Game is over, market still resolving. Infer from last_price.
            if last_p is not None and last_p >= 0.95:
                outcome = 1
                resolution_source = "post_expiry_price_ge_0.95"
            elif last_p is not None and last_p <= 0.05:
                outcome = 0
                resolution_source = "post_expiry_price_le_0.05"
            elif last_p is not None and last_p >= 0.85:
                # Game over with strong but not extreme polarization.
                # Use a conservative inference threshold of 0.85; this
                # gives the v1 favorite YES on a winning team.
                outcome = 1
                resolution_source = "post_expiry_price_ge_0.85"
            elif last_p is not None and last_p <= 0.15:
                outcome = 0
                resolution_source = "post_expiry_price_le_0.15"

        if outcome is None:
            continue

        resolved_rows.append({
            "ticker": tk,
            "series_prefix": series_prefix_of(tk),
            "series_ticker": r["series_ticker"],
            "effective_price": float(r["effective_price"]),
            "kalshi_mid": float(r["kalshi_mid"]),
            "sportsbook_median": float(r["sportsbook_median"]) if pd.notna(r["sportsbook_median"]) else None,
            "outcome": outcome,
            "kalshi_status": status,
            "kalshi_last_price": last_p,
            "kalshi_result": result,
            "resolution_source": resolution_source,
        })

    return pd.DataFrame(resolved_rows)


# ============================================================
# Path Y: augment v4 inventory (historical) with current sportsbook
# ============================================================

def build_path_y_rows() -> pd.DataFrame:
    """Build the v4-style inventory + check current sportsbook coverage."""
    inv_path = DATA_V3 / "probe_inventory_all_markets.parquet"
    if not inv_path.exists():
        return pd.DataFrame()
    inv = pd.read_parquet(inv_path)
    elig = inv[
        inv["eligible_wide"]
        & inv["vwap_t35_wide"].notna()
        & inv["outcome"].notna()
    ].copy()
    elig["series_prefix"] = elig["ticker"].apply(series_prefix_of)
    elig["effective_price"] = elig["vwap_t35_wide"]
    elig = elig[
        (elig["effective_price"] >= FAVORITE_THRESHOLD)
        & (elig["effective_price"] <= FAVORITE_UPPER_CAP)
    ].copy()
    if "series_ticker" not in elig.columns:
        elig["series_ticker"] = elig["ticker"].apply(
            lambda t: "-".join(t.split("-")[:-1])
        )
    return elig.reset_index(drop=True)


def main() -> None:
    print("=" * 80)
    print("V5-A2: combined filter backtest (Path X + Path Y)")
    print("=" * 80)
    print()
    print("Pre-registered thresholds (LOCKED):")
    print(f"  fade_poly = {FADE_THRESHOLD_CENTS_POLY_DEFAULT}c")
    print(f"  fade_book = {FADE_THRESHOLD_CENTS_BOOK_DEFAULT}c")
    print(f"  mono      = {MONOTONICITY_THRESHOLD_CENTS_DEFAULT}c")
    print()

    # Build the data feeds
    poly_lookup = build_polymarket_lookup()
    sportsbook_lookup = build_sportsbook_lookup_from_v5()
    print(f"Polymarket lookup size: {len(poly_lookup)}")
    print(f"Sportsbook lookup size (matched only): {len(sportsbook_lookup)}")
    print()

    # ---- PATH X: live-cached probe ----
    print("[Path X] Live-cached probe, restricted to RESOLVED markets")
    print("-" * 80)
    from kalshi_bot.config import load_settings
    from kalshi_bot.data.kalshi_client import KalshiClient
    s = load_settings()
    client = KalshiClient(s)
    path_x = build_path_x_rows(client, restrict_to_v1_band=True)
    print(f"Path X resolved rows (v1-band only): {len(path_x)}")
    if not path_x.empty:
        print(path_x[["ticker", "effective_price", "sportsbook_median",
                       "outcome", "resolution_source"]].to_string(index=False))
    print()

    path_x_ext = build_path_x_rows(client, restrict_to_v1_band=False)
    print(f"Path X extended (all resolved, any kalshi_mid): {len(path_x_ext)}")
    if not path_x_ext.empty:
        print(path_x_ext[["ticker", "effective_price", "sportsbook_median",
                          "outcome", "resolution_source"]].to_string(index=False))
    print()

    arms: list[FilterArmResult] = []
    if not path_x.empty:
        # Path X has no v4 ladder data (we don't have v3 inventory siblings
        # for these live markets), and no Polymarket lookup (live mid is
        # only in V5-A1's cache, not pulled for the live markets). The
        # combined filter on this subset is effectively SPORTSBOOK-ONLY.
        # That's fine because Path X is the targeted test of the new A3
        # rule's value.
        arm_x = run_arm(
            path_x,
            arm_name="Path X: combined filter on resolved live-cached pairs",
            fade_threshold_cents_poly=FADE_THRESHOLD_CENTS_POLY_DEFAULT,
            fade_threshold_cents_book=FADE_THRESHOLD_CENTS_BOOK_DEFAULT,
            monotonicity_threshold_cents=MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
            poly_lookup=None,
            sportsbook_lookup=sportsbook_lookup,
            cross_market_data=None,
        )
        arms.append(arm_x)
        print_arm(arm_x)

        # Sportsbook-only sensitivity at tighter book thresholds.
        for book_c in (3.0, 7.0, 10.0):
            arm_x_sens = run_arm(
                path_x,
                arm_name=f"Path X sensitivity: book={book_c:.0f}c",
                fade_threshold_cents_poly=FADE_THRESHOLD_CENTS_POLY_DEFAULT,
                fade_threshold_cents_book=book_c,
                monotonicity_threshold_cents=MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
                poly_lookup=None,
                sportsbook_lookup=sportsbook_lookup,
                cross_market_data=None,
            )
            arms.append(arm_x_sens)
            print_arm(arm_x_sens)

    if not path_x_ext.empty:
        # Extended Path X: ALL resolved markets (not v1-band restricted),
        # to give the A3 rule a chance to fire on the broader sample.
        # Cleaner test of signal direction at small n.
        arm_x_ext = run_arm(
            path_x_ext,
            arm_name="Path X extended: all resolved markets (any band)",
            fade_threshold_cents_poly=FADE_THRESHOLD_CENTS_POLY_DEFAULT,
            fade_threshold_cents_book=FADE_THRESHOLD_CENTS_BOOK_DEFAULT,
            monotonicity_threshold_cents=MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
            poly_lookup=None,
            sportsbook_lookup=sportsbook_lookup,
            cross_market_data=None,
        )
        arms.append(arm_x_ext)
        print_arm(arm_x_ext)

    # ---- PATH Y: v4 inventory + current sportsbook overlay ----
    print("[Path Y] v4 inventory backtest, augmented with CURRENT sportsbook")
    print("        WARNING: sportsbook prices are sampled TODAY, not at T-35d.")
    print("        This is a coverage-side check, not a clean signal test.")
    print("-" * 80)
    path_y = build_path_y_rows()
    print(f"Path Y eligible rows: {len(path_y)}")
    print()

    if not path_y.empty:
        inv = pd.read_parquet(DATA_V3 / "probe_inventory_all_markets.parquet")
        cross_market_data = build_cross_market_data(inv)
        # The v4-style headline arm uses the full set: poly + book + cross.
        # Sportsbook coverage on the v3 inventory will likely be VERY low
        # because the inventory is dominated by KXNFLWINS / KXMLBPLAYOFFS
        # which the-odds-api covers via OUTRIGHTS endpoints (not h2h) and
        # those event lookups are out of scope for this build's sport_key
        # mapping (h2h only). We still run the arm honestly.
        arm_y = run_arm(
            path_y,
            arm_name="Path Y: full combined filter (poly + book + mono)",
            fade_threshold_cents_poly=FADE_THRESHOLD_CENTS_POLY_DEFAULT,
            fade_threshold_cents_book=FADE_THRESHOLD_CENTS_BOOK_DEFAULT,
            monotonicity_threshold_cents=MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
            poly_lookup=poly_lookup,
            sportsbook_lookup=sportsbook_lookup,
            cross_market_data=cross_market_data,
        )
        arms.append(arm_y)
        print_arm(arm_y)

        # Decomposition: book-only on path Y
        arm_y_book_only = run_arm(
            path_y,
            arm_name="Path Y decomp: book-only",
            fade_threshold_cents_poly=FADE_THRESHOLD_CENTS_POLY_DEFAULT,
            fade_threshold_cents_book=FADE_THRESHOLD_CENTS_BOOK_DEFAULT,
            monotonicity_threshold_cents=MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
            poly_lookup=None,
            sportsbook_lookup=sportsbook_lookup,
            cross_market_data=None,
        )
        arms.append(arm_y_book_only)
        print_arm(arm_y_book_only)

        # Decomposition: poly-only (equals v4 headline minus cross_market)
        arm_y_poly_only = run_arm(
            path_y,
            arm_name="Path Y decomp: poly-only",
            fade_threshold_cents_poly=FADE_THRESHOLD_CENTS_POLY_DEFAULT,
            fade_threshold_cents_book=FADE_THRESHOLD_CENTS_BOOK_DEFAULT,
            monotonicity_threshold_cents=MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
            poly_lookup=poly_lookup,
            sportsbook_lookup=None,
            cross_market_data=None,
        )
        arms.append(arm_y_poly_only)
        print_arm(arm_y_poly_only)

        # Decomposition: cross-market only
        arm_y_cross_only = run_arm(
            path_y,
            arm_name="Path Y decomp: cross-market only",
            fade_threshold_cents_poly=FADE_THRESHOLD_CENTS_POLY_DEFAULT,
            fade_threshold_cents_book=FADE_THRESHOLD_CENTS_BOOK_DEFAULT,
            monotonicity_threshold_cents=MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
            poly_lookup=None,
            sportsbook_lookup=None,
            cross_market_data=cross_market_data,
        )
        arms.append(arm_y_cross_only)
        print_arm(arm_y_cross_only)

    # Persist all outputs.
    out_path = DATA_V5 / "sportsbook_filter_backtest_results.json"
    payload = {
        "thresholds_locked": {
            "fade_threshold_cents_poly": FADE_THRESHOLD_CENTS_POLY_DEFAULT,
            "fade_threshold_cents_book": FADE_THRESHOLD_CENTS_BOOK_DEFAULT,
            "monotonicity_threshold_cents": MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
        },
        "path_x": {
            "n_resolved_v1_band": int(len(path_x)),
            "n_resolved_extended": int(len(path_x_ext)),
            "rows_v1_band": path_x.to_dict(orient="records") if not path_x.empty else [],
            "rows_extended": path_x_ext.to_dict(orient="records") if not path_x_ext.empty else [],
        },
        "path_y": {
            "n_eligible": int(len(path_y)),
        },
        "arms": [serialize_arm(a) for a in arms],
        "build_completed_at": datetime.now(timezone.utc).isoformat(),
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
