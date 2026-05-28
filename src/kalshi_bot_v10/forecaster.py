"""V10-B multi-vendor LLM forecaster.

Per B2 Section 3-4: each available vendor receives the same locked prompt.
Outputs are Platt-scaled per vendor then averaged.

Platt scaling (B2 Section 3, t_k = sqrt(3) = 1.7320508 for all vendors):
    logit(x) = log(x / (1 - x))
    sigmoid(x) = 1 / (1 + exp(-x))
    p_platt = sigmoid(sqrt(3) * logit(p_raw))

p_raw is clipped to [0.01, 0.99] before logit to prevent infinities.

Supervisor pass (B3 Revision 3): triggered when spread > 0.25 (raised
from B2's 0.15 to reduce Opus calls and stay within cost budget).

B2 Section 8 (F3): NO Kalshi prices in the prompt. The system and user
prompts are reproduced verbatim from B2 Section 4.
"""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from typing import Any

from kalshi_bot_v10.vendor_clients import (
    call_anthropic_haiku,
    call_anthropic_opus,
    call_deepseek_flash,
    call_gemini_flash,
    call_groq_llama70b,
)

# ---------------------------------------------------------------------------
# Locked prompt templates (B2 Section 4 -- do not modify)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are an expert forecaster. Estimate the probability of YES resolution"
    " for the prediction market described. Do not search for or incorporate any"
    " prediction market price, sportsbook line, or betting market consensus into"
    " your estimate. Your estimate must be independent of market prices.\n\n"
    "Use any available search or retrieval tools to find current factual context"
    " relevant to the market outcome. Only use information dated before the"
    " market's close_time.\n\n"
    "Output JSON only, with this exact schema:\n"
    "{\"reasoning\": \"<your step-by-step analysis>\","
    " \"p_yes\": <float between 0.01 and 0.99>}\n\n"
    "Do not output exactly 0.50 unless you genuinely believe the event is a coin"
    " flip after careful analysis. Use two-decimal precision (e.g., 0.43, not 0.4"
    " or 43%)."
)


def _build_user_prompt(
    market: dict[str, Any],
    snippets: list[dict[str, Any]],
    now_utc: datetime,
) -> str:
    """Build the per-market user prompt with Tavily context injected."""
    close_time = market.get("close_time", "unknown")
    title = market.get("title", market.get("ticker", "unknown"))
    rules = market.get("rules_primary", market.get("subtitle", "No rules text available."))

    lines = [
        f"Market: {title}",
        f"Resolution rules: {rules}",
        f"Market closes (resolves): {close_time} UTC",
        f"Today's date and time: {now_utc.strftime('%Y-%m-%d %H:%M')} UTC",
    ]

    if snippets:
        lines.append("\nRelevant recent context:")
        for i, s in enumerate(snippets, 1):
            date_str = f" ({s['date']})" if s.get("date") else ""
            lines.append(f"\n[{i}] {s['title']}{date_str}")
            lines.append(s.get("snippet", ""))

    lines.append("\nPlease research this question and provide your probability estimate. Output JSON only.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Platt scaling
# ---------------------------------------------------------------------------

_PLATT_T = math.sqrt(3)  # 1.7320508; locked per B2 Section 3


def _logit(p: float) -> float:
    p = max(0.01, min(0.99, p))
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def platt_scale(p_raw: float) -> float:
    """Apply Platt scaling: sigmoid(sqrt(3) * logit(p_raw)), p_raw clipped to [0.01, 0.99]."""
    return _sigmoid(_PLATT_T * _logit(p_raw))


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_p_yes(raw_text: str) -> float | None:
    """Extract p_yes float from vendor response text.

    Tries JSON parse first; falls back to regex extraction.
    Returns None if p_yes cannot be extracted.
    """
    # Try direct JSON parse after stripping code fences
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw_text).strip()
    try:
        data = json.loads(cleaned)
        val = data.get("p_yes")
        if val is not None:
            return float(val)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Regex fallback: look for "p_yes": 0.XX pattern
    match = re.search(r'"p_yes"\s*:\s*([0-9]*\.?[0-9]+)', raw_text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass

    return None


# ---------------------------------------------------------------------------
# Vendor dispatch table
# ---------------------------------------------------------------------------

_VENDOR_FUNCS = [
    ("haiku-4.5", call_anthropic_haiku, "ANTHROPIC_API_KEY"),
    ("gemini-2.5-flash", call_gemini_flash, "GEMINI_API_KEY"),
    ("deepseek-chat", call_deepseek_flash, "DEEPSEEK_API_KEY"),
    ("groq-llama-3.1-70b", call_groq_llama70b, "GROQ_API_KEY"),
]


# ---------------------------------------------------------------------------
# Main forecaster
# ---------------------------------------------------------------------------

def forecast_market(
    market: dict[str, Any],
    tavily_snippets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run multi-vendor LLM forecast for one market.

    Args:
        market: Kalshi market dict with keys: ticker, title, rules_primary,
                close_time (ISO string), series_ticker.
        tavily_snippets: Pre-filtered snippets from tavily_judge.filter_snippets().

    Returns dict:
        p_llm_ensemble:     float (mean of Platt-scaled vendor outputs)
        p_per_vendor:       dict[vendor_name -> p_raw]
        platt_per_vendor:   dict[vendor_name -> p_platt]
        spread:             float (max(p_raw) - min(p_raw) across succeeded vendors)
        supervisor_eligible: bool (True if spread > 0.25 per B3 Revision 3)
        supervisor_result:  dict or None (Opus synthesis if triggered)
        vendors_skipped:    list[str] (vendors missing keys or errored)
        vendors_used:       list[str]
        cost_total:         float (USD, sum across all vendor calls)
        parse_failures:     int (vendor calls that returned unparseable output)
    """
    now_utc = datetime.now(timezone.utc)
    user_prompt = _build_user_prompt(market, tavily_snippets, now_utc)
    prompt = {"system": _SYSTEM_PROMPT, "user": user_prompt}

    p_per_vendor: dict[str, float] = {}
    platt_per_vendor: dict[str, float] = {}
    vendors_skipped: list[str] = []
    vendors_used: list[str] = []
    cost_total = 0.0
    parse_failures = 0

    for vendor_name, call_fn, env_key in _VENDOR_FUNCS:
        # Skip if key is absent
        if not os.environ.get(env_key, ""):
            vendors_skipped.append(f"{vendor_name} (key absent: {env_key})")
            continue

        result = call_fn(prompt)
        cost_total += result.get("cost_usd", 0.0)

        if result.get("error"):
            vendors_skipped.append(f"{vendor_name} (error: {result['error']})")
            continue

        p_raw = _parse_p_yes(result.get("raw_text", ""))
        if p_raw is None:
            vendors_skipped.append(f"{vendor_name} (parse failure)")
            parse_failures += 1
            continue

        # Clip to valid range
        p_raw = max(0.01, min(0.99, p_raw))
        p_platt = platt_scale(p_raw)

        p_per_vendor[vendor_name] = p_raw
        platt_per_vendor[vendor_name] = p_platt
        vendors_used.append(vendor_name)

    # Compute ensemble
    if not platt_per_vendor:
        # All vendors failed; return a sentinel
        return {
            "p_llm_ensemble": 0.5,
            "p_per_vendor": {},
            "platt_per_vendor": {},
            "spread": 0.0,
            "supervisor_eligible": False,
            "supervisor_result": None,
            "vendors_skipped": vendors_skipped,
            "vendors_used": [],
            "cost_total": round(cost_total, 6),
            "parse_failures": parse_failures,
            "error": "all_vendors_failed",
        }

    p_vals = list(platt_per_vendor.values())
    p_llm_ensemble = sum(p_vals) / len(p_vals)

    raw_vals = list(p_per_vendor.values())
    spread = max(raw_vals) - min(raw_vals) if len(raw_vals) > 1 else 0.0

    # B3 Revision 3: supervisor triggers at spread > 0.25 (raised from B2's 0.15)
    supervisor_eligible = spread > 0.25
    supervisor_result = None

    if supervisor_eligible and os.environ.get("ANTHROPIC_API_KEY", ""):
        supervisor_result = _run_supervisor(market, tavily_snippets, p_per_vendor, p_llm_ensemble, cost_total)
        if supervisor_result and supervisor_result.get("p_supervisor") is not None:
            # Blend supervisor into ensemble: mean of all sub-agent + supervisor
            p_sup = supervisor_result["p_supervisor"]
            all_probs = p_vals + [p_sup]
            p_llm_ensemble = sum(all_probs) / len(all_probs)
            cost_total += supervisor_result.get("cost_usd", 0.0)

    return {
        "p_llm_ensemble": round(p_llm_ensemble, 4),
        "p_per_vendor": {k: round(v, 4) for k, v in p_per_vendor.items()},
        "platt_per_vendor": {k: round(v, 4) for k, v in platt_per_vendor.items()},
        "spread": round(spread, 4),
        "supervisor_eligible": supervisor_eligible,
        "supervisor_result": supervisor_result,
        "vendors_skipped": vendors_skipped,
        "vendors_used": vendors_used,
        "cost_total": round(cost_total, 6),
        "parse_failures": parse_failures,
        "error": None,
    }


def _run_supervisor(
    market: dict[str, Any],
    snippets: list[dict[str, Any]],
    p_per_vendor: dict[str, float],
    current_ensemble: float,
    cost_so_far: float,
) -> dict[str, Any] | None:
    """Run Opus 4.7 supervisor when sub-agent spread exceeds 0.25.

    Per B2 Section 3 supervisor pass: Opus reads all sub-agent reasonings
    and outputs a synthesis probability p_supervisor.
    """
    title = market.get("title", market.get("ticker", "unknown"))
    vendor_summary = "\n".join(
        f"  {k}: p_raw={v:.3f}" for k, v in p_per_vendor.items()
    )

    sup_user = (
        f"Market: {title}\n\n"
        "Sub-agent probability estimates show high spread (> 0.25).\n"
        "Sub-agent raw estimates:\n"
        f"{vendor_summary}\n\n"
        f"Current ensemble (mean Platt-scaled): {current_ensemble:.3f}\n\n"
        "As supervisor, review the sub-agent estimates and provide a synthesis"
        " probability. Consider: which sub-agents may be miscalibrated? Is there"
        " information asymmetry driving the spread?\n\n"
        "Output JSON only:\n"
        "{\"synthesis_reasoning\": \"<brief>\", \"p_supervisor\": <float 0.01-0.99>}"
    )
    sup_prompt = {"system": _SYSTEM_PROMPT, "user": sup_user}
    result = call_anthropic_opus(sup_prompt)

    cost = result.get("cost_usd", 0.0)
    if result.get("error"):
        return {"p_supervisor": None, "cost_usd": cost, "error": result["error"]}

    p_sup = _parse_p_yes(result.get("raw_text", ""))
    # Try to also extract p_supervisor key if p_yes not found
    if p_sup is None:
        raw = result.get("raw_text", "")
        match = re.search(r'"p_supervisor"\s*:\s*([0-9]*\.?[0-9]+)', raw)
        if match:
            try:
                p_sup = float(match.group(1))
            except ValueError:
                pass

    return {
        "p_supervisor": p_sup,
        "cost_usd": cost,
        "error": None,
    }
