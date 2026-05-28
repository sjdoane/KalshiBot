"""CLI entry point for the v14 daemon. Just defers to the module."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from kalshi_bot_v14.daemon import main


if __name__ == "__main__":
    raise SystemExit(main())
