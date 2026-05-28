"""V4-D Section 5 sketch: internal Kalshi cross-market consistency probe.

For KXNFLWINS ladders, P(wins >= k) should be monotonically NON-INCREASING in k.
Any violation is a candidate arb (the cheaper higher-threshold contract is
mispriced low, OR the more expensive lower-threshold contract is mispriced high).

This script:
  1. Audits all team-season ladders with >= 3 thresholds at T-35d.
  2. Counts monotonicity violations.
  3. For each violation, computes the realized direction
     (did the cheap upper or rich lower resolve in the "right" way?).
  4. Aggregates the realized-edge implication.

The output is FEASIBILITY EVIDENCE for the cross-market backup approach.
No trading, no leakage into v1.

Output: data/v4/cross_market_consistency.json
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_V3 = REPO_ROOT / "data" / "v3"
OUT = REPO_ROOT / "data" / "v4" / "cross_market_consistency.json"


def parse_nflwins(t: str) -> tuple[str | None, str | None, int | None]:
    """KXNFLWINS-{TEAM}-{YEAR}-T{N}."""
    parts = t.split("-")
    if len(parts) == 4 and parts[3].startswith("T"):
        thresh_str = parts[3].lstrip("T")
        return parts[1], parts[2], int(thresh_str) if thresh_str.isdigit() else None
    return None, None, None


def parse_mlbwins(t: str) -> tuple[str | None, str | None, int | None]:
    """KXMLBWINS-{TEAM}-{YEAR}-T{N}.  Same format as NFL."""
    parts = t.split("-")
    if len(parts) == 4 and parts[3].startswith("T"):
        thresh_str = parts[3].lstrip("T")
        return parts[1], parts[2], int(thresh_str) if thresh_str.isdigit() else None
    return None, None, None


def audit_ladders(df: pd.DataFrame, prefix: str, parser) -> dict:
    series = df[df["ticker"].str.startswith(prefix)].copy()
    parsed = series["ticker"].apply(lambda t: pd.Series(parser(t)))
    series[["team", "year", "threshold"]] = parsed
    eligible = series.dropna(subset=["team", "year", "threshold", "vwap_t35_narrow"])

    out = {
        "series_prefix": prefix,
        "n_total_markets": int(len(series)),
        "n_with_price_at_t35": int(len(eligible)),
    }

    grouped = eligible.groupby(["team", "year"])
    team_seasons = []
    for (team, year), grp in grouped:
        grp = grp.sort_values("threshold").reset_index(drop=True)
        if len(grp) < 3:
            continue
        viols: list[dict] = []
        for i in range(len(grp) - 1):
            p_lo = float(grp.iloc[i]["vwap_t35_narrow"])
            p_hi = float(grp.iloc[i + 1]["vwap_t35_narrow"])
            # Strict violation: higher threshold has strictly higher price (more than 1c noise).
            if p_hi > p_lo + 0.01:
                viols.append({
                    "team": team,
                    "year": year,
                    "low_threshold": int(grp.iloc[i]["threshold"]),
                    "low_price": p_lo,
                    "low_resolved_yes": int(grp.iloc[i]["outcome"]) if pd.notna(grp.iloc[i]["outcome"]) else None,
                    "low_ticker": grp.iloc[i]["ticker"],
                    "high_threshold": int(grp.iloc[i + 1]["threshold"]),
                    "high_price": p_hi,
                    "high_resolved_yes": int(grp.iloc[i + 1]["outcome"]) if pd.notna(grp.iloc[i + 1]["outcome"]) else None,
                    "high_ticker": grp.iloc[i + 1]["ticker"],
                    "spread_cents": (p_hi - p_lo) * 100.0,
                })
        team_seasons.append({
            "team": team,
            "year": year,
            "n_thresholds": int(len(grp)),
            "n_violations": int(len(viols)),
            "violations": viols,
        })

    n_ladders = len(team_seasons)
    n_with_violations = sum(1 for ts in team_seasons if ts["n_violations"] > 0)
    n_total_violations = sum(ts["n_violations"] for ts in team_seasons)
    n_adjacent_pairs = sum(ts["n_thresholds"] - 1 for ts in team_seasons)
    spread_cents_list = [v["spread_cents"] for ts in team_seasons for v in ts["violations"]]

    # Realized check: for each violation, which side won?
    #   The "cheap upper" gambit: buy the higher-threshold contract that is mispriced HIGH.
    #     Wait, no. The violation is p_high > p_low. A monotone fix has p_high <= p_low.
    #     If actually true p_high should be LOWER, the high-threshold contract is OVERPRICED.
    #     A trader would SELL/short YES on the high-threshold, OR buy NO.
    #     The realized "correct" outcome: high-threshold resolves NO more often than low.
    #     i.e. high_resolved_yes <= low_resolved_yes.
    short_high_correct = 0
    short_high_wrong = 0
    short_high_neutral = 0
    for ts in team_seasons:
        for v in ts["violations"]:
            lo = v["low_resolved_yes"]
            hi = v["high_resolved_yes"]
            if lo is None or hi is None:
                continue
            if hi < lo:
                short_high_correct += 1  # high resolved NO, low resolved YES: monotone fix vindicated
            elif hi == lo:
                short_high_neutral += 1
            else:
                short_high_wrong += 1

    out.update({
        "n_team_seasons_with_3plus_thresholds": n_ladders,
        "n_team_seasons_with_violations": n_with_violations,
        "n_total_violations": n_total_violations,
        "n_adjacent_pairs_audited": n_adjacent_pairs,
        "violation_rate_per_pair": n_total_violations / n_adjacent_pairs if n_adjacent_pairs else None,
        "violation_spread_cents_mean": float(pd.Series(spread_cents_list).mean()) if spread_cents_list else None,
        "violation_spread_cents_median": float(pd.Series(spread_cents_list).median()) if spread_cents_list else None,
        "violation_spread_cents_p75": float(pd.Series(spread_cents_list).quantile(0.75)) if spread_cents_list else None,
        "violation_spread_cents_p95": float(pd.Series(spread_cents_list).quantile(0.95)) if spread_cents_list else None,
        "realized_short_high_correct": short_high_correct,
        "realized_short_high_wrong": short_high_wrong,
        "realized_short_high_neutral": short_high_neutral,
        "realized_short_high_hit_rate_excluding_ties": (
            short_high_correct / (short_high_correct + short_high_wrong)
            if (short_high_correct + short_high_wrong) > 0
            else None
        ),
        "team_seasons_summary": [
            {"team": ts["team"], "year": ts["year"], "n_thresholds": ts["n_thresholds"], "n_violations": ts["n_violations"]}
            for ts in team_seasons
        ],
        "sample_violations": [
            v
            for ts in team_seasons
            for v in ts["violations"]
        ][:15],
    })
    return out


def main() -> None:
    df = pd.read_parquet(DATA_V3 / "probe_inventory_all_markets.parquet")
    summary = {
        "nflwins": audit_ladders(df, "KXNFLWINS", parse_nflwins),
        "mlbwins": audit_ladders(df, "KXMLBWINS", parse_mlbwins),
        "nbawins": audit_ladders(df, "KXNBAWINS", parse_nflwins),  # same format
    }

    with open(OUT, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"Wrote {OUT}\n")
    for series, s in summary.items():
        print(f"=== {series.upper()} ===")
        print(f"  Total markets: {s['n_total_markets']}")
        print(f"  With T-35 price: {s['n_with_price_at_t35']}")
        print(f"  Team-seasons with 3+ thresholds: {s['n_team_seasons_with_3plus_thresholds']}")
        print(f"  Team-seasons with at least one violation: {s['n_team_seasons_with_violations']}")
        print(f"  Total adjacent-pair violations: {s['n_total_violations']} of {s['n_adjacent_pairs_audited']} pairs ({s['violation_rate_per_pair']:.1%} if {s['n_adjacent_pairs_audited']} else 'NA')")
        if s["violation_spread_cents_mean"]:
            print(f"  Violation spread (cents): mean={s['violation_spread_cents_mean']:.1f}, median={s['violation_spread_cents_median']:.1f}, p75={s['violation_spread_cents_p75']:.1f}, p95={s['violation_spread_cents_p95']:.1f}")
        if s["realized_short_high_hit_rate_excluding_ties"] is not None:
            print(f"  Realized 'short the high-threshold' hit rate (excluding ties): {s['realized_short_high_hit_rate_excluding_ties']:.1%}")
            print(f"    (correct={s['realized_short_high_correct']}, wrong={s['realized_short_high_wrong']}, ties={s['realized_short_high_neutral']})")
        print()


if __name__ == "__main__":
    main()
