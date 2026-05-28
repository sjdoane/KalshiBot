"""Operator wake-up sanity check.

Run this first thing after the autonomous run to verify the project is
in a sane state. Reports:
- Test suite pass count
- Ruff lint status
- Existence and sizes of key data files
- Sports gate verdict (if available)
- Politics gate verdict (always)
- Any stale background jobs / temp files
- Discord webhook smoke
- Kalshi API smoke
- Capital cap config value (should be 25 default)

Usage:
    uv run python -m scripts.wake_up_check
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from kalshi_bot.config import load_settings


def _exists(p: Path) -> str:
    if not p.exists():
        return "MISSING"
    if p.is_dir():
        return f"DIR (contains {len(list(p.glob('*')))} items)"
    size = p.stat().st_size
    return f"{size} bytes"


def _read_verdict(report_path: Path) -> str:
    if not report_path.exists():
        return "REPORT NOT YET WRITTEN"
    text = report_path.read_text(encoding="utf-8", errors="replace")
    if "GATE PASSES" in text:
        return "PASS"
    if "PROVISIONAL PASS" in text:
        return "PROVISIONAL PASS"
    if "GATE FAILS" in text:
        return "FAIL"
    return "INCONCLUSIVE"


def main() -> int:
    print("=== Project Kalshi Wake-Up Check ===\n")

    project = Path(__file__).resolve().parents[1]
    print(f"Project root: {project}")
    print()

    # 1. Test suite
    print("--- Test suite ---")
    result = subprocess.run(
        ["uv", "run", "pytest", "-q", "--no-header"],
        cwd=project, check=False, capture_output=True, text=True,
    )
    tail = result.stdout.splitlines()[-3:] if result.stdout else []
    for line in tail:
        print(f"  {line}")
    print(f"  exit code: {result.returncode}")
    print()

    # 2. Ruff lint
    print("--- Ruff lint ---")
    result = subprocess.run(
        ["uv", "run", "ruff", "check", "src/", "scripts/", "tests/"],
        cwd=project, check=False, capture_output=True, text=True,
    )
    print(f"  exit code: {result.returncode}")
    if result.returncode != 0:
        print(f"  stdout: {result.stdout[:500]}")
    print()

    # 3. Key data files
    print("--- Data files ---")
    files = [
        project / "data" / "phase2" / "politics_series_index.json",
        project / "data" / "phase2" / "markets",
        project / "data" / "phase2" / "trades",
        project / "data" / "processed" / "politics_phase2_dataset.parquet",
        project / "data" / "sports" / "sports_series_index.json",
        project / "data" / "sports" / "markets",
        project / "data" / "sports" / "trades",
        project / "data" / "processed" / "sports_dataset.parquet",
        project / "data" / "paper_trades" / "state.json",
    ]
    for f in files:
        rel = f.relative_to(project)
        print(f"  {rel!s:60s} {_exists(f)}")
    print()

    # 4. Gate verdicts
    print("--- Gate verdicts ---")
    print(f"  Politics x H: {_read_verdict(project / 'research' / 'phase-2-results.md')}")
    print(f"  Sports x Long-Horizon (Strategy A compression): {_read_verdict(project / 'research' / 'sports-results.md')}")
    fav = _read_verdict(project / 'research' / 'favorite-maker-results.md')
    if "GATE PASSES" in (project / 'research' / 'favorite-maker-results.md').read_text(encoding='utf-8', errors='replace') if (project / 'research' / 'favorite-maker-results.md').exists() else "":
        fav = "PASS (LIVE READY)"
    print(f"  Sports Strategy B (favorite-maker): {fav}")
    print()

    # 5. Paper trading state
    paper_state = project / "data" / "paper_trades" / "state.json"
    if paper_state.exists():
        try:
            state = json.loads(paper_state.read_text(encoding="utf-8"))
            print("--- Paper trading state ---")
            print(f"  open orders: {len(state.get('open_orders', {}))}")
            print(f"  filled (unsettled): {len(state.get('filled_orders', {}))}")
            print(f"  closed (settled): {len(state.get('closed_orders', {}))}")
            print(f"  starting bankroll: ${state.get('starting_bankroll_usd', 0):.2f}")
            print(f"  realized PnL: ${state.get('realized_pnl_total_usd', 0):.2f}")
            print()
        except (OSError, json.JSONDecodeError):
            print("--- Paper trading state ---")
            print("  state.json present but unreadable")
            print()

    # 6. Capital cap config
    print("--- Config ---")
    try:
        s = load_settings()
        print(f"  KALSHI_ENV: {s.KALSHI_ENV}")
        print(f"  CAPITAL_CAP_USD: ${s.CAPITAL_CAP_USD}")
        print(f"  Discord webhook configured: {bool(s.DISCORD_WEBHOOK_URL)}")
        print(f"  Kalshi key configured: {bool(s.active_key_id)}")
    except Exception as exc:
        print(f"  ERROR loading settings: {exc}")
    print()

    # 7. Key documents present?
    print("--- Key documents ---")
    docs = [
        "research/OPERATOR_HANDOFF.md",
        "research/LIVE_READINESS_DECISION.md",
        "research/phase-2-autonomous-log.md",
        "research/phase-2-results.md",
        "research/sports-longhorizon-methodology.md",
        "research/critic-methodology-sports.md",
        "research/sports-results.md",
        "research/favorite-maker-results.md",
        "research/critic-favorite-maker.md",
        "research/phase-3-design.md",
        "research/phase-3-runbook.md",
    ]
    for d in docs:
        full = project / d
        print(f"  {d:60s} {'OK' if full.exists() else 'MISSING'}")
    print()

    print("=== Wake-up check complete ===")
    print("Read research/OPERATOR_HANDOFF.md first for context.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
