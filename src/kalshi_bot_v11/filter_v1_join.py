"""Post-hoc join of v5 filter shadow log vs v1 order log.

Produces a cross-table that pairs each v5-filter decision (from
data/live_trades/v5_filter_shadow_log.jsonl) with the corresponding v1
order outcome (from data/live_trades/state.json), per v11 Phase 1.5
methodology lock v2 Section 9.

v1_decision is a 5-state enum per the lock:
    placed_and_filled, placed_and_expired, placed_and_cancelled,
    placed_and_rejected, not_placed

A sixth implementation state, placed_and_resting, distinguishes
currently-open orders that have not yet reached a terminal status.

This module is pure (no I/O) so the script wrapper in scripts/v11/ is
trivially testable.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


MATCH_WINDOW_SECONDS = 5 * 60


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def derive_v1_decision(intent: dict[str, Any]) -> str:
    """Map a v1 intent record to one of the v1_decision enum values.

    The classification is mutually exclusive and exhaustive against
    the state.json schema observed at v1 deployment time.
    """
    if int(intent.get("filled_count") or 0) > 0:
        return "placed_and_filled"
    if intent.get("cancelled_ts"):
        return "placed_and_cancelled"
    if not intent.get("acked_ts"):
        return "placed_and_rejected"
    if intent.get("resolution_ts"):
        return "placed_and_expired"
    return "placed_and_resting"


def collect_intents(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull all v1 intents from state.json into a single list.

    The state.json schema groups intents by lifecycle (intents,
    resting, filled, closed). For the cross-table we want a single
    flat list to scan per shadow-log row.
    """
    intents: list[dict[str, Any]] = []
    for pool_name in ("intents", "resting", "filled", "closed"):
        pool = state.get(pool_name) or {}
        for intent_id, record in pool.items():
            intents.append(record)
    return intents


def match_intent(
    intents: list[dict[str, Any]],
    ticker: str,
    timestamp: datetime,
    window_seconds: int = MATCH_WINDOW_SECONDS,
) -> dict[str, Any] | None:
    """Find a v1 intent for the given ticker whose placed_ts is within
    +/- window_seconds of the shadow-log timestamp.

    If multiple match, return the one with placed_ts closest to the
    shadow-log timestamp.
    """
    window = timedelta(seconds=window_seconds)
    best: tuple[timedelta, dict[str, Any]] | None = None
    for intent in intents:
        if intent.get("ticker") != ticker:
            continue
        placed_ts = _parse_ts(intent.get("placed_ts"))
        if placed_ts is None:
            continue
        delta = abs(placed_ts - timestamp)
        if delta > window:
            continue
        if best is None or delta < best[0]:
            best = (delta, intent)
    return best[1] if best else None


def derive_arm_decisions(
    shadow_row: dict[str, Any],
) -> tuple[bool | None, bool | None]:
    """Reconstruct the per-arm fade decisions from a shadow-log row.

    Returns (sportsbook_arm_decision, polymarket_arm_decision). Each is
    None when the corresponding arm had no signal (poly_mid or
    sportsbook_implied missing); True when the arm fired its fade rule;
    False when the arm participated but did not fire.
    """
    fired = set(shadow_row.get("fired_rules") or [])
    sportsbook_implied = shadow_row.get("sportsbook_implied")
    poly_mid = shadow_row.get("poly_mid")
    sportsbook_arm = (
        ("sportsbook_fade" in fired) if sportsbook_implied is not None else None
    )
    polymarket_arm = (
        ("polymarket_fade" in fired) if poly_mid is not None else None
    )
    return sportsbook_arm, polymarket_arm


def build_cross_row(
    shadow_row: dict[str, Any], intents: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compose one output JSONL row from a shadow-log row plus the
    matching v1 intent (if any).
    """
    ts = _parse_ts(shadow_row.get("timestamp"))
    if ts is None:
        raise ValueError(f"shadow log row missing timestamp: {shadow_row!r}")
    ticker = shadow_row.get("ticker", "")
    intent = match_intent(intents, ticker, ts)
    v1_decision = derive_v1_decision(intent) if intent else "not_placed"
    sportsbook_arm, polymarket_arm = derive_arm_decisions(shadow_row)
    return {
        "timestamp": shadow_row.get("timestamp"),
        "ticker": ticker,
        "v1_decision": v1_decision,
        "shadow_filter_decision": bool(shadow_row.get("should_trade")),
        "sportsbook_arm_decision": sportsbook_arm,
        "polymarket_arm_decision": polymarket_arm,
    }


def join_logs(
    shadow_log_lines: list[str], state: dict[str, Any]
) -> list[dict[str, Any]]:
    """Take iterable shadow-log JSONL lines + a state.json dict and
    return the cross-table rows.

    Pure function. The script wrapper provides file I/O.
    """
    intents = collect_intents(state)
    rows: list[dict[str, Any]] = []
    for raw in shadow_log_lines:
        raw = raw.strip()
        if not raw:
            continue
        shadow_row = json.loads(raw)
        rows.append(build_cross_row(shadow_row, intents))
    return rows


def run_join(
    shadow_log_path: Path | str,
    state_json_path: Path | str,
    output_path: Path | str,
) -> int:
    """Read inputs, join, write JSONL output. Returns number of rows
    written. Creates the output parent directory if missing.
    """
    shadow_log_path = Path(shadow_log_path)
    state_json_path = Path(state_json_path)
    output_path = Path(output_path)
    with shadow_log_path.open("r", encoding="utf-8") as f:
        shadow_lines = f.readlines()
    with state_json_path.open("r", encoding="utf-8") as f:
        state = json.load(f)
    rows = join_logs(shadow_lines, state)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return len(rows)
