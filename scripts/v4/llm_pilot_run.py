"""V4-C LLM pilot runner.

Per the brief, run the Anthropic SDK against 25 sampled Kalshi markets with two
prompt variants (with-price and no-price). Cheap pass on Haiku, spot-check on
Opus 4.7. Record probabilities, latency, tokens, cost, rationales.

Hard cost guard: total spend stays under $5. Default Haiku-only run is ~$0.10.
Opus spot-check on n=5 markets adds ~$1.50 - $2.

Usage:
    uv run python -m scripts.v4.llm_pilot_run --model haiku
    uv run python -m scripts.v4.llm_pilot_run --model opus --opus-spot-n 5
    uv run python -m scripts.v4.llm_pilot_run --model both --opus-spot-n 5
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

SAMPLE_PATH = PROJECT_ROOT / "data" / "v4" / "llm_pilot_sample.parquet"
OUT_PATH = PROJECT_ROOT / "data" / "v4" / "llm_pilot_results.parquet"
META_PATH = PROJECT_ROOT / "data" / "v4" / "llm_pilot_results_meta.json"
BLOCKED_PATH = PROJECT_ROOT / "data" / "v4" / "llm_pilot_BLOCKED.txt"

# Anthropic model identifiers and pricing per the brief.
HAIKU_MODEL = "claude-haiku-4-5"
OPUS_MODEL = "claude-opus-4-7"

# Per million tokens.
PRICING = {
    HAIKU_MODEL: {"input": 1.00, "output": 5.00},
    OPUS_MODEL: {"input": 15.00, "output": 75.00},
}

# Max output tokens. Each forecast is short.
MAX_TOKENS = 600

PROB_RE = re.compile(r"PROB\s*[:=]\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
RATIONALE_RE = re.compile(r"RATIONALE\s*[:=]\s*(.+)", re.IGNORECASE | re.DOTALL)


def build_prompt(row: pd.Series, *, include_price: bool, variant: str) -> str:
    """Two base prompt variants (A=with-price, B=no-price) plus pivot variants C (no-memory)
    and D (chain-of-thought scaffolding).
    """
    title = row.get("title") or ""
    rules_primary = row.get("rules_primary") or ""
    rules_secondary = row.get("rules_secondary") or ""
    event_subtitle = row.get("event_subtitle") or ""
    yes_sub_title = row.get("yes_sub_title") or ""
    no_sub_title = row.get("no_sub_title") or ""

    open_time = pd.Timestamp(row["open_time"])
    close_time = pd.Timestamp(row["close_time"])

    parts: list[str] = []
    if variant == "A":
        parts.append(
            "You are a probabilistic forecaster. "
            f"The following Kalshi market is currently trading at {row['favorite_price']:.4f}. "
            "Based on the rules and evidence available, what is your best estimate of P(YES)?"
        )
    elif variant == "B":
        parts.append(
            "You are a probabilistic forecaster. "
            "Based on the rules and evidence available, what is your best estimate of P(YES)?"
        )
    elif variant == "C":
        parts.append(
            "You are a probabilistic forecaster. Do not use your memory of past events or "
            "their actual outcomes; reason only from the market description and rules provided "
            "below. What is your best estimate of P(YES)?"
        )
    elif variant == "D":
        parts.append(
            "You are a probabilistic forecaster. First, list the most important "
            "facts and considerations relevant to this market. Then estimate the probability."
        )
    else:
        raise ValueError(f"Unknown variant {variant}")

    parts.append("")
    parts.append(f"Market: {title}")
    if event_subtitle:
        parts.append(f"Subtitle: {event_subtitle}")
    parts.append(f"Rules: {rules_primary}")
    if rules_secondary:
        parts.append(f"Settlement: {rules_secondary}")
    if yes_sub_title:
        parts.append(f"YES means: {yes_sub_title}")
    if no_sub_title and no_sub_title != yes_sub_title:
        parts.append(f"NO means: {no_sub_title}")
    parts.append(f"Open date: {open_time.strftime('%Y-%m-%d')}")
    parts.append(f"Close date: {close_time.strftime('%Y-%m-%d')}")
    parts.append("")
    if variant == "D":
        parts.append(
            "Output your reasoning, then the probability. Use this exact format:\n"
            "FACTS:\n- <fact 1>\n- <fact 2>\n...\nPROB: <value between 0.0 and 1.0>\n"
            "RATIONALE: <one paragraph>"
        )
    else:
        parts.append(
            "Output ONLY a probability between 0.0 and 1.0, followed by a one-paragraph rationale. "
            "Format:\nPROB: <value>\nRATIONALE: <text>"
        )

    return "\n".join(parts)


def parse_response(text: str) -> tuple[float | None, str]:
    """Extract probability and rationale from response."""
    prob_match = PROB_RE.search(text)
    prob = None
    if prob_match:
        try:
            v = float(prob_match.group(1))
            if 0.0 <= v <= 1.0:
                prob = v
        except ValueError:
            pass
    rationale_match = RATIONALE_RE.search(text)
    rationale = rationale_match.group(1).strip() if rationale_match else text.strip()
    return prob, rationale[:500]


def get_api_key() -> str | None:
    """Best-effort find the ANTHROPIC_API_KEY in process env or Windows user-env."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    # On Windows the User-scope env var may not be inherited into this process.
    try:
        import subprocess
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             '[System.Environment]::GetEnvironmentVariable("ANTHROPIC_API_KEY","User")'],
            capture_output=True, text=True, timeout=5,
        )
        key = r.stdout.strip()
        if key:
            return key
    except Exception:
        pass
    return None


def run_one(client, model: str, prompt: str, ticker: str, variant: str) -> dict:
    """Run a single LLM forecast and return record."""
    t0 = time.time()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        latency = time.time() - t0
        text = response.content[0].text if response.content else ""
        usage = response.usage
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        cost = (input_tokens * PRICING[model]["input"] + output_tokens * PRICING[model]["output"]) / 1_000_000
        prob, rationale = parse_response(text)
        return {
            "ticker": ticker,
            "model": model,
            "variant": variant,
            "prompt_len": len(prompt),
            "llm_prob": prob,
            "llm_rationale": rationale[:500],
            "raw_response_first_300": text[:300],
            "latency_s": latency,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
            "error": None,
        }
    except Exception as e:
        return {
            "ticker": ticker,
            "model": model,
            "variant": variant,
            "prompt_len": len(prompt),
            "llm_prob": None,
            "llm_rationale": None,
            "raw_response_first_300": None,
            "latency_s": time.time() - t0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "error": str(e)[:200],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["haiku", "opus", "both"], default="haiku")
    parser.add_argument("--variants", nargs="+", default=["A", "B"], choices=["A", "B", "C", "D"])
    parser.add_argument("--opus-spot-n", type=int, default=5)
    parser.add_argument(
        "--max-cost-usd", type=float, default=5.0,
        help="Hard cost guard. Run aborts if exceeded.",
    )
    parser.add_argument(
        "--label", type=str, default="primary",
        help="Suffix to write distinct results parquets per pivot.",
    )
    args = parser.parse_args()

    api_key = get_api_key()
    if not api_key:
        BLOCKED_PATH.write_text(
            "ANTHROPIC_API_KEY not found in process env or Windows User-scope env.\n"
            "V4-C blocked. Orchestrator: please provide credentials and rerun.\n"
        )
        print(f"BLOCKED. Wrote note to {BLOCKED_PATH}")
        sys.exit(2)

    # Import only after we know we have a key.
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)

    df = pd.read_parquet(SAMPLE_PATH)
    print(f"Loaded sample n={len(df)} from {SAMPLE_PATH}")
    print(f"Bucket counts: {df['cutoff_bucket'].value_counts().to_dict()}")

    # Decide which (model, ticker) pairs to run.
    plan: list[tuple[str, pd.Series]] = []
    if args.model in ("haiku", "both"):
        for _, row in df.iterrows():
            plan.append((HAIKU_MODEL, row))
    if args.model in ("opus", "both"):
        # Spot-check: pick a balanced slice across all 3 buckets.
        # Heuristic: take ~proportional samples per bucket; top up to args.opus_spot_n if needed.
        parts = []
        per_bucket = max(1, args.opus_spot_n // df["cutoff_bucket"].nunique())
        for bucket, g in df.groupby("cutoff_bucket"):
            parts.append(g.sample(n=min(per_bucket, len(g)), random_state=42))
        spot = pd.concat(parts).reset_index(drop=True)
        if len(spot) > args.opus_spot_n:
            spot = spot.sample(n=args.opus_spot_n, random_state=42).reset_index(drop=True)
        elif len(spot) < args.opus_spot_n:
            remaining = df[~df["ticker"].isin(spot["ticker"])]
            need = args.opus_spot_n - len(spot)
            extra = remaining.sample(n=min(need, len(remaining)), random_state=42)
            spot = pd.concat([spot, extra]).reset_index(drop=True)
        for _, row in spot.iterrows():
            plan.append((OPUS_MODEL, row))
        print(f"Opus spot tickers ({len(spot)}): {list(spot['ticker'])}")
        print(f"  bucket counts: {spot['cutoff_bucket'].value_counts().to_dict()}")

    # Run.
    rows: list[dict] = []
    total_cost = 0.0
    for i, (model, row) in enumerate(plan, 1):
        for variant in args.variants:
            prompt = build_prompt(row, include_price=(variant == "A"), variant=variant)
            rec = run_one(client, model, prompt, row["ticker"], variant)
            # Attach context columns.
            rec["cutoff_bucket"] = row["cutoff_bucket"]
            rec["outcome"] = int(row["outcome"])
            rec["kalshi_price"] = float(row["favorite_price"])
            rec["close_time"] = str(row["close_time"])
            rec["league"] = row["league"]
            rows.append(rec)
            total_cost += rec["cost_usd"]
            print(
                f"  [{i}/{len(plan)}] {model.split('-')[1]} | {variant} | {row['ticker']} | "
                f"prob={rec['llm_prob']} | tok in={rec['input_tokens']} out={rec['output_tokens']} | "
                f"cost=${rec['cost_usd']:.4f} | total=${total_cost:.3f}"
            )
            if total_cost > args.max_cost_usd:
                print(f"COST GUARD HIT (>{args.max_cost_usd}). Stopping run.")
                break
        if total_cost > args.max_cost_usd:
            break

    res = pd.DataFrame(rows)
    out_path = OUT_PATH if args.label == "primary" else OUT_PATH.with_name(f"llm_pilot_results_{args.label}.parquet")
    meta_path = META_PATH if args.label == "primary" else META_PATH.with_name(f"llm_pilot_results_meta_{args.label}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    res.to_parquet(out_path, index=False)

    meta = {
        "n_calls": len(res),
        "total_cost_usd": total_cost,
        "by_model": res.groupby("model").size().to_dict(),
        "by_variant": res.groupby("variant").size().to_dict(),
        "n_with_prob": int(res["llm_prob"].notna().sum()),
        "n_with_error": int(res["error"].notna().sum()),
        "args": vars(args),
    }
    meta_path.write_text(json.dumps(meta, indent=2, default=str))
    print(f"\nWrote {len(res)} rows to {out_path}")
    print(f"Total cost: ${total_cost:.4f}")
    print(f"Probs parsed: {meta['n_with_prob']} / {len(res)}")
    print(f"Errors: {meta['n_with_error']}")


if __name__ == "__main__":
    main()
