"""V4-F LLM-as-forecaster module.

Public API:

    from kalshi_bot_v4.llm_forecaster import Forecaster, ForecastResult

    forecaster = Forecaster(model="claude-haiku-4-5", prompt_variant="C")
    result = forecaster.forecast(market_row)
    print(result.prob_yes, result.rationale)

The Forecaster wraps the Anthropic SDK and applies the V4-C pilot's
Prompt C as the base prompt: no Kalshi price shown, explicit
"do-not-use-your-memory" injunction. Prompt CR is the same with a
Wikipedia retrieval-augmented context block appended.

Caching: results are cached in data/v4/llm_forecast_cache.parquet
keyed by (ticker, model, prompt_variant). A cache hit skips the API
call and returns the previously-computed result. The cache file is
append-safe but not multi-writer safe.

Hard constraints:
- ANTHROPIC_API_KEY from process env or Windows User-scope fallback
- Cost guard not enforced inside the forecaster; the caller is
  responsible for tracking cumulative spend and stopping when the
  budget is exhausted (see scripts/v4/run_llm_gate.py).
- No em-dashes anywhere in this file (per CLAUDE.md hard rule).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import pandas as pd

# Resolve project root for the cache file
_HERE = Path(__file__).resolve()
PROJECT_ROOT = _HERE.parents[2]
CACHE_PATH = PROJECT_ROOT / "data" / "v4" / "llm_forecast_cache.parquet"

# Anthropic model identifiers + pricing as of v4 build.
HAIKU_MODEL = "claude-haiku-4-5"
OPUS_MODEL = "claude-opus-4-7"

# Per million tokens (USD)
PRICING = {
    HAIKU_MODEL: {"input": 1.00, "output": 5.00},
    OPUS_MODEL: {"input": 15.00, "output": 75.00},
}

# Allow alternate model IDs that the SDK may resolve (e.g. dated variants).
def _model_pricing(model: str) -> dict:
    if model in PRICING:
        return PRICING[model]
    if "haiku" in model:
        return PRICING[HAIKU_MODEL]
    if "opus" in model:
        return PRICING[OPUS_MODEL]
    # Fallback: Sonnet-ish pricing (mid-tier). Will likely cost more than budgeted.
    return {"input": 3.00, "output": 15.00}


MAX_TOKENS = 600

PROB_RE = re.compile(r"PROB\s*[:=]\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
RATIONALE_RE = re.compile(r"RATIONALE\s*[:=]\s*(.+)", re.IGNORECASE | re.DOTALL)


class ForecastResult(NamedTuple):
    """A single LLM forecast result. NamedTuple per brief."""

    ticker: str
    prob_yes: float
    rationale: str
    model_name: str
    prompt_variant: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int


def _get_api_key() -> str | None:
    """Find ANTHROPIC_API_KEY in process env or Windows User-scope env.

    V4-C confirmed the key is in Windows User-scope; the process env may
    not inherit it depending on shell. This is the documented fallback.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             '[System.Environment]::GetEnvironmentVariable("ANTHROPIC_API_KEY","User")'],
            capture_output=True, text=True, timeout=5,
        )
        k = r.stdout.strip()
        if k:
            return k
    except Exception:
        pass
    return None


def _parse_response(text: str) -> tuple[float | None, str]:
    """Extract probability and rationale from LLM response."""
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


def _fetch_wikipedia_summary(query: str, timeout: float = 5.0) -> str | None:
    """Fetch a Wikipedia summary for the given query.

    Used by Prompt CR. Returns up to 1000 characters of the article
    extract, or None on failure. Best-effort; failures are silent.
    """
    try:
        # 1. Search for the page title
        search_url = (
            "https://en.wikipedia.org/w/api.php?"
            "action=opensearch&format=json&limit=1&search="
            + urllib.parse.quote(query)
        )
        req = urllib.request.Request(
            search_url,
            headers={"User-Agent": "ProjectKalshi-v4-research/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data or len(data) < 2 or not data[1]:
            return None
        page_title = data[1][0]

        # 2. Fetch the summary
        summary_url = (
            "https://en.wikipedia.org/api/rest_v1/page/summary/"
            + urllib.parse.quote(page_title.replace(" ", "_"))
        )
        req2 = urllib.request.Request(
            summary_url,
            headers={"User-Agent": "ProjectKalshi-v4-research/1.0"},
        )
        with urllib.request.urlopen(req2, timeout=timeout) as resp:
            sd = json.loads(resp.read().decode("utf-8"))
        extract = sd.get("extract", "")
        if not extract:
            return None
        return extract[:1000]
    except Exception:
        return None


def _build_prompt(market_row: dict, prompt_variant: str, retrieval_text: str | None = None) -> str:
    """Build the forecast prompt.

    Variants:
      C  = Prompt C from V4-C pilot. No price, no-memory injunction.
      CR = Prompt C plus retrieval-augmented Wikipedia context.
      C2 = Prompt-sensitivity variant 2 (rephrasing).
      C3 = Prompt-sensitivity variant 3 (rephrasing).
      WP = Prompt-with-price control (S-B2 anchor test).
      ANON = Prompt C with ticker name AND precise dates stripped.

    The market_row dict must NOT contain favorite_price for variants
    other than WP. The Forecaster enforces this.
    """
    title = market_row.get("title") or ""
    rules_primary = market_row.get("rules_primary") or ""
    rules_secondary = market_row.get("rules_secondary") or ""
    event_subtitle = market_row.get("event_subtitle") or ""
    yes_sub_title = market_row.get("yes_sub_title") or ""
    no_sub_title = market_row.get("no_sub_title") or ""

    open_time = pd.Timestamp(market_row["open_time"])
    close_time = pd.Timestamp(market_row["close_time"])

    parts: list[str] = []

    if prompt_variant == "C":
        parts.append(
            "You are a probabilistic forecaster. Do not use your memory of past events "
            "or their actual outcomes; reason only from the market description and rules "
            "provided below. What is your best estimate of P(YES)?"
        )
    elif prompt_variant == "CR":
        parts.append(
            "You are a probabilistic forecaster. Do not use your memory of past events "
            "or their actual outcomes; reason only from the market description, rules, "
            "and the background context provided below. What is your best estimate of P(YES)?"
        )
    elif prompt_variant == "C2":
        parts.append(
            "Act as a calibrated probability forecaster. Ignore anything you may "
            "remember about how this event actually resolved. Using only the market "
            "rules and description, give your P(YES) estimate."
        )
    elif prompt_variant == "C3":
        parts.append(
            "You are evaluating a binary prediction market. Set aside any prior "
            "knowledge of the actual outcome; ground your forecast strictly in the "
            "rules and description here. Provide P(YES)."
        )
    elif prompt_variant == "WP":
        # Price-anchor control: prompt with price visible.
        if "favorite_price" not in market_row:
            raise ValueError("WP variant requires 'favorite_price' in market_row")
        parts.append(
            "You are a probabilistic forecaster. The favorite side of the following "
            f"Kalshi market is currently trading at {float(market_row['favorite_price']):.4f}. "
            "Based on the rules and evidence available, what is your best estimate of P(YES)?"
        )
    elif prompt_variant == "ANON":
        # Anonymized: no ticker, no precise dates.
        parts.append(
            "You are a probabilistic forecaster. Do not use your memory of past events. "
            "What is your best estimate of P(YES) for the following anonymous market?"
        )
    else:
        raise ValueError(f"Unknown prompt variant: {prompt_variant}")

    parts.append("")
    if prompt_variant != "ANON":
        parts.append(f"Market: {title}")
        if event_subtitle:
            parts.append(f"Subtitle: {event_subtitle}")
    else:
        # Strip identifying titles; only keep rules + subtitle category
        if event_subtitle:
            parts.append(f"Subtitle: {event_subtitle}")

    parts.append(f"Rules: {rules_primary}")
    if rules_secondary:
        parts.append(f"Settlement: {rules_secondary}")
    if yes_sub_title:
        parts.append(f"YES means: {yes_sub_title}")
    if no_sub_title and no_sub_title != yes_sub_title:
        parts.append(f"NO means: {no_sub_title}")

    if prompt_variant == "ANON":
        parts.append(f"Open year: {open_time.year}")
        parts.append(f"Close year: {close_time.year}")
    else:
        parts.append(f"Open date: {open_time.strftime('%Y-%m-%d')}")
        parts.append(f"Close date: {close_time.strftime('%Y-%m-%d')}")

    if prompt_variant == "CR" and retrieval_text:
        parts.append("")
        parts.append("Background context (from Wikipedia, for reference; may be outdated):")
        parts.append(retrieval_text)

    parts.append("")
    parts.append(
        "Output ONLY a probability between 0.0 and 1.0, followed by a one-paragraph "
        "rationale. Format:\nPROB: <value>\nRATIONALE: <text>"
    )
    return "\n".join(parts)


@dataclass
class _CacheEntry:
    """Internal cache record."""
    ticker: str
    model: str
    prompt_variant: str
    prob_yes: float
    rationale: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    timestamp: str


class Forecaster:
    """LLM-as-forecaster wrapper.

    Args:
        model: Anthropic model identifier. Default Haiku 4.5.
        prompt_variant: Prompt template (C, CR, C2, C3, WP, ANON).
        client: Optional pre-built Anthropic client (else build via API key).
        cache_path: Optional override of the cache parquet path.
        enable_cache: If False, skip cache reads/writes.
        retrieve_for_cr: If True and variant is CR, fetch Wikipedia for the title.
    """

    def __init__(
        self,
        model: str = HAIKU_MODEL,
        prompt_variant: str = "C",
        *,
        client=None,
        cache_path: Path | None = None,
        enable_cache: bool = True,
        retrieve_for_cr: bool = True,
    ) -> None:
        self.model = model
        self.prompt_variant = prompt_variant
        self.cache_path = cache_path or CACHE_PATH
        self.enable_cache = enable_cache
        self.retrieve_for_cr = retrieve_for_cr

        if client is None:
            api_key = _get_api_key()
            if not api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not found in process env or Windows User-scope env."
                )
            from anthropic import Anthropic
            client = Anthropic(api_key=api_key)
        self.client = client

        # Load cache (lazy)
        self._cache: dict[tuple[str, str, str], _CacheEntry] = {}
        if self.enable_cache and self.cache_path.exists():
            self._load_cache()

    def _load_cache(self) -> None:
        try:
            df = pd.read_parquet(self.cache_path)
        except Exception:
            return
        for _, row in df.iterrows():
            key = (row["ticker"], row["model"], row["prompt_variant"])
            self._cache[key] = _CacheEntry(
                ticker=str(row["ticker"]),
                model=str(row["model"]),
                prompt_variant=str(row["prompt_variant"]),
                prob_yes=float(row["prob_yes"]),
                rationale=str(row.get("rationale", "")),
                input_tokens=int(row.get("input_tokens", 0)),
                output_tokens=int(row.get("output_tokens", 0)),
                cost_usd=float(row.get("cost_usd", 0.0)),
                latency_ms=int(row.get("latency_ms", 0)),
                timestamp=str(row.get("timestamp", "")),
            )

    def _append_cache(self, entry: _CacheEntry) -> None:
        if not self.enable_cache:
            return
        # Build a 1-row frame
        row = {
            "ticker": entry.ticker,
            "model": entry.model,
            "prompt_variant": entry.prompt_variant,
            "prob_yes": entry.prob_yes,
            "rationale": entry.rationale,
            "input_tokens": entry.input_tokens,
            "output_tokens": entry.output_tokens,
            "cost_usd": entry.cost_usd,
            "latency_ms": entry.latency_ms,
            "timestamp": entry.timestamp,
        }
        new_df = pd.DataFrame([row])
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        if self.cache_path.exists():
            try:
                existing = pd.read_parquet(self.cache_path)
                # Drop any prior row with the same key (overwrite semantics)
                mask = ~(
                    (existing["ticker"] == entry.ticker)
                    & (existing["model"] == entry.model)
                    & (existing["prompt_variant"] == entry.prompt_variant)
                )
                merged = pd.concat([existing[mask], new_df], ignore_index=True)
            except Exception:
                merged = new_df
        else:
            merged = new_df
        merged.to_parquet(self.cache_path, index=False)
        self._cache[(entry.ticker, entry.model, entry.prompt_variant)] = entry

    def forecast(self, market_row: dict) -> ForecastResult:
        """Run a single forecast for a market.

        market_row must contain: ticker, title, rules_primary,
        rules_secondary, open_time, close_time, event_subtitle,
        yes_sub_title, no_sub_title. Must NOT contain favorite_price
        unless prompt_variant is WP (price-anchor control).
        """
        ticker = market_row["ticker"]
        if self.prompt_variant != "WP" and "favorite_price" in market_row and market_row["favorite_price"] is not None:
            # Defensive: do not leak price into non-WP prompts.
            scrubbed = dict(market_row)
            scrubbed.pop("favorite_price", None)
            market_row = scrubbed

        cache_key = (ticker, self.model, self.prompt_variant)
        if self.enable_cache and cache_key in self._cache:
            e = self._cache[cache_key]
            return ForecastResult(
                ticker=e.ticker,
                prob_yes=e.prob_yes,
                rationale=e.rationale,
                model_name=e.model,
                prompt_variant=e.prompt_variant,
                input_tokens=e.input_tokens,
                output_tokens=e.output_tokens,
                cost_usd=0.0,  # zero-cost on a cache hit
                latency_ms=0,
            )

        # Retrieval for Prompt CR
        retrieval_text = None
        if self.prompt_variant == "CR" and self.retrieve_for_cr:
            # Derive a query from the market title and subtitle.
            title = market_row.get("title") or ""
            subtitle = market_row.get("event_subtitle") or ""
            # Heuristic: use the subtitle if it's specific; else use the title.
            query = subtitle if (subtitle and len(subtitle) < 80) else title
            # Strip generic words
            query = query.replace("Will the", "").replace("pro football team", "").strip()
            if query:
                retrieval_text = _fetch_wikipedia_summary(query)

        prompt = _build_prompt(market_row, self.prompt_variant, retrieval_text)

        t0 = time.time()
        response = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = int((time.time() - t0) * 1000)
        text = response.content[0].text if response.content else ""
        usage = response.usage
        input_tokens = int(getattr(usage, "input_tokens", 0))
        output_tokens = int(getattr(usage, "output_tokens", 0))
        pricing = _model_pricing(self.model)
        cost_usd = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000

        prob, rationale = _parse_response(text)
        if prob is None:
            # Defensive fallback: parse fail -> treat as 0.5 with note
            prob = 0.5
            rationale = "PARSE_FAIL: " + (text[:400] if text else "")

        entry = _CacheEntry(
            ticker=ticker,
            model=self.model,
            prompt_variant=self.prompt_variant,
            prob_yes=prob,
            rationale=rationale,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            timestamp=pd.Timestamp.utcnow().isoformat(),
        )
        self._append_cache(entry)
        return ForecastResult(
            ticker=ticker,
            prob_yes=prob,
            rationale=rationale,
            model_name=self.model,
            prompt_variant=self.prompt_variant,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )
