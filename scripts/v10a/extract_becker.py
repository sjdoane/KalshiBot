"""Extract Becker data.tar.zst using Python zstandard + tarfile.

The official scripts/install-tools.sh + scripts/download.sh pipeline assumes
brew/apt to install zstd CLI, which is Linux/Mac only. On Windows we use
Python's zstandard package (already added via uv add zstandard).

Streams the .tar.zst through zstandard.ZstdDecompressor -> tarfile.open
without saving the intermediate .tar to disk. Extracts to
prediction-market-analysis/data/.

Run via prediction-market-analysis/.venv Python (uv environment).
"""
from __future__ import annotations

import sys
import tarfile
import time
from pathlib import Path

import zstandard

REPO_ROOT = Path(__file__).resolve().parents[2]
BECKER_DIR = REPO_ROOT / "prediction-market-analysis"
ARCHIVE = BECKER_DIR / "data.tar.zst"
EXTRACT_TO = BECKER_DIR  # extracts data/ subdir into BECKER_DIR
SENTINEL = BECKER_DIR / "data" / ".download_complete"


def main() -> None:
    if not ARCHIVE.exists():
        raise SystemExit(f"Archive not found: {ARCHIVE}")
    if SENTINEL.exists():
        print(f"Sentinel exists: {SENTINEL}. Skipping extraction.")
        return

    print(f"Extracting {ARCHIVE} ({ARCHIVE.stat().st_size / 1e9:.2f} GB) ...")
    started = time.time()

    dctx = zstandard.ZstdDecompressor()
    with open(ARCHIVE, "rb") as compressed:
        with dctx.stream_reader(compressed) as decompressed:
            # tarfile in "r|" mode reads from a non-seekable stream (streaming).
            with tarfile.open(fileobj=decompressed, mode="r|") as tar:
                count = 0
                last_print = started
                for member in tar:
                    tar.extract(member, path=EXTRACT_TO)
                    count += 1
                    now = time.time()
                    if now - last_print > 5:
                        print(
                            f"  extracted {count} members; "
                            f"elapsed {now - started:.0f}s; "
                            f"last: {member.name}"
                        )
                        last_print = now

    print(f"Done. Extracted {count} members in {time.time() - started:.1f} s.")
    # Write sentinel to mark completion
    sentinel_dir = SENTINEL.parent
    sentinel_dir.mkdir(parents=True, exist_ok=True)
    SENTINEL.touch()
    print(f"Sentinel: {SENTINEL}")


if __name__ == "__main__":
    main()
