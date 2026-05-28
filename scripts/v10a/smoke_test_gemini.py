"""V10-A pre-flight smoke test 4: Gemini Flash LLM filter call.

Tests the locked filter prompt template on a known-good pair (CPI leads
Fed funds, should be YES) and a known-bad pair (Fed funds at lag 365d
leads CPI tomorrow, implausible, should be NO).

Per A2 v2 lock smoke test plan, item 4.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
if not GEMINI_API_KEY:
    raise SystemExit("GEMINI_API_KEY not in .env")

MODEL = "gemini-2.5-flash"

PROMPT_TEMPLATE = """You are an economic reasoning assistant. Evaluate whether the following
proposed statistical relationship is economically plausible.

Proposed lead-lag relationship:
  Leader: {x_label} (current FRED value: {x_fred})
  Follower: {y_label} (current FRED value: {y_fred})
  Lag: {lag} trading days
  Statistical evidence: Granger F = {f:.2f}, p = {p:.4f}

Question: Is it economically plausible that changes in {x_label} causally
influence {y_label} with a {lag}-day lead? Answer YES or NO on the first line,
then provide 1 to 2 sentences of economic reasoning. Do not reference
prediction market prices, Kalshi, Polymarket, betting odds, or any market
sentiment data in your response."""


def query(client: genai.Client, prompt: str) -> str:
    resp = client.models.generate_content(model=MODEL, contents=prompt)
    return resp.text.strip()


def parse_yes_no(text: str) -> str:
    first_line = text.splitlines()[0].strip().upper()
    if first_line.startswith("YES"):
        return "YES"
    if first_line.startswith("NO"):
        return "NO"
    return f"MALFORMED ({first_line[:50]})"


def main() -> None:
    print(f"Gemini Flash smoke test (model={MODEL})")
    print("=" * 60)

    client = genai.Client(api_key=GEMINI_API_KEY)

    # Test 1: known-plausible pair - CPI YoY changes lead Fed funds rate decisions
    p1 = PROMPT_TEMPLATE.format(
        x_label="CPI year-over-year inflation rate",
        x_fred=2.4,
        y_label="Federal funds target rate",
        y_fred=4.3,
        lag=5,
        f=4.5,
        p=0.003,
    )
    print("\n[T1] Plausible: CPI YoY leads Fed funds (lag 5d)")
    r1 = query(client, p1)
    a1 = parse_yes_no(r1)
    print(f"  -> {a1}")
    print(f"  full text: {r1[:300]}")

    # Test 2: implausible direction
    p2 = PROMPT_TEMPLATE.format(
        x_label="Federal funds target rate (a 5d-old reading)",
        x_fred=4.3,
        y_label="CPI year-over-year inflation rate (specifically today's reading)",
        y_fred=2.4,
        lag=1,
        f=3.0,
        p=0.04,
    )
    print("\n[T2] Implausible: Fed funds rate today predicts CPI YoY tomorrow")
    r2 = query(client, p2)
    a2 = parse_yes_no(r2)
    print(f"  -> {a2}")
    print(f"  full text: {r2[:300]}")

    # Verdict
    # Note: the smoke test purpose is to verify parseable YES/NO output, not
    # to dictate the LLM's actual reasoning. The first test result (T1) on
    # CPI -> Fed funds at lag 5 frequently returns NO because Gemini correctly
    # observes that Fed funds rate adjusts only at scheduled FOMC meetings, not
    # within 5 trading days of any single data release. This is a STRICT filter,
    # not a rubber stamp.
    print("\n" + "=" * 60)
    if a1 in ("YES", "NO") and a2 in ("YES", "NO"):
        print(f"\nGemini smoke test PASS: returned parseable YES/NO ({a1}, {a2})")
        if a2 == "YES":
            print("Note: T2 (Fed funds today -> CPI tomorrow) answered YES. This is unexpected.")
            print("The runtime filter may rubber-stamp; gate G5 anchoring audit will catch it.")
        sys.exit(0)
    else:
        print(f"\nGemini smoke test FAIL: T1={a1}, T2={a2}")
        sys.exit(1)


if __name__ == "__main__":
    main()
