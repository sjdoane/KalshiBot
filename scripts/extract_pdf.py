"""One-shot helper: dump PDF text to UTF-8 file. Used for the Burgi paper."""

from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: extract_pdf.py <input.pdf> <output.txt>", file=sys.stderr)
        return 1
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    reader = PdfReader(str(src))
    lines: list[str] = [f"pages={len(reader.pages)}\n"]
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        lines.append(f"\n=== PAGE {i + 1} ({len(text)} chars) ===\n")
        lines.append(text)
    dst.write_text("".join(lines), encoding="utf-8")
    print(f"wrote {dst} ({dst.stat().st_size} bytes, {len(reader.pages)} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
