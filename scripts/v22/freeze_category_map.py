"""v22 category-map freeze (pre-screen, structural fields ONLY).

Per research/v22/00-methodology-lock.md (critic H-5): the frozen
rebrand-unified prefix-to-category map = the existing v10a mapper's prefix
assignments (get_group), unified across the KX-rebrand break by
ticker-structure rules only, committed with hash BEFORE the screen script
exists.

Construction (locked):
- Enumerate distinct event-ticker prefixes (regexp_extract(event_ticker,
  '^([A-Z0-9]+)', 1)) over the v22 qualifying market population
  (open_time >= 2024-11-01, finalized yes/no, lifetime >= 10d, close_time
  < 2025-11-01 and < 2028; the same population for P3 minus the lifetime
  floor is a superset by prefix, so both screens share this map). NO trade
  or outcome aggregates are read; markets-table structural columns only.
- canonical_prefix: if a prefix does not start with 'KX' and 'KX'+prefix
  also appears, unify to 'KX'+prefix (rebrand rule, ticker structure only).
- group = get_group(canonical_prefix without manipulation, i.e. the v10a
  mapper applied to the canonical prefix).
- graveyard flag: group in {Media, Entertainment, Other} (the v21-dead
  cells; EXCLUDED from the P1 pooled estimand and the P3 population per
  the lock).

Run (Windows):
  & "C:\\Users\\SamJD\\OneDrive\\Desktop\\AI Projects\\Project Kalshi\\.venv-kronos\\Scripts\\python.exe" "C:\\Users\\SamJD\\OneDrive\\Desktop\\AI Projects\\Project Kalshi\\scripts\\v22\\freeze_category_map.py"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

BASE = Path(r"C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
BECKER = BASE / "prediction-market-analysis"
MARKETS_DIR = BECKER / "data" / "kalshi" / "markets"
OUT_PATH = BASE / "research" / "v22" / "category_map.json"

sys.path.insert(0, str(BECKER))
from src.analysis.kalshi.util.categories import get_group  # noqa: E402

GRAVEYARD_GROUPS = {"Media", "Entertainment", "Other"}


def main() -> None:
    con = duckdb.connect(":memory:")
    con.execute("PRAGMA threads=8")
    con.execute("SET TimeZone='UTC'")
    q = f"""
        SELECT DISTINCT regexp_extract(event_ticker, '^([A-Z0-9]+)', 1) AS prefix
        FROM '{MARKETS_DIR.as_posix()}/*.parquet'
        WHERE status = 'finalized' AND result IN ('yes','no')
          AND open_time >= TIMESTAMP '2024-11-01'
          AND close_time < TIMESTAMP '2025-11-01'
          AND close_time < TIMESTAMP '2028-01-01'
          AND event_ticker IS NOT NULL AND event_ticker != ''
    """
    prefixes = sorted({r[0] for r in con.execute(q).fetchall() if r[0]})
    have = set(prefixes)

    entries = {}
    n_unified = 0
    for p in prefixes:
        if not p.startswith("KX") and ("KX" + p) in have:
            canonical = "KX" + p
            n_unified += 1
        else:
            canonical = p
        group = get_group(canonical)
        entries[p] = {
            "canonical": canonical,
            "group": group,
            "graveyard": group in GRAVEYARD_GROUPS,
        }

    out = {
        "built": "2026-06-11",
        "rule": (
            "distinct event-ticker prefixes over the v22 qualifying market "
            "population; rebrand unification prefix -> KX+prefix when both "
            "exist; group = v10a get_group(canonical); structural fields only"
        ),
        "n_prefixes": len(entries),
        "n_rebrand_unified": n_unified,
        "graveyard_groups": sorted(GRAVEYARD_GROUPS),
        "map": entries,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    groups: dict[str, int] = {}
    for e in entries.values():
        groups[e["group"]] = groups.get(e["group"], 0) + 1
    print(f"[freeze] {len(entries)} prefixes ({n_unified} rebrand-unified) -> {OUT_PATH}")
    for g in sorted(groups, key=groups.get, reverse=True)[:12]:
        flag = " (GRAVEYARD)" if g in GRAVEYARD_GROUPS else ""
        print(f"  {g}: {groups[g]}{flag}")


if __name__ == "__main__":
    main()
