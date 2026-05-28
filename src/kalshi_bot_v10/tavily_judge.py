"""Haiku 4.5 post-retrieval judge for Tavily snippets.

Per B3 Revision 2: after Tavily search, each snippet is screened by
Claude Haiku 4.5 to remove any content that:
  - Mentions Kalshi/Polymarket/sportsbook prices or contracts
  - Contains information dated AFTER the market's close_time

Flagged snippets are removed BEFORE they are assembled into the LLM
forecaster prompt. The forecaster never sees flagged content.

B2 Section 5 foreknowledge guard: if judge returns YES on a snippet
it is excluded from the prompt AND logged in the audit_log.

Warning threshold: if more than 30% of snippets are flagged,
log a warning that the judge may be broken (over-aggressive filtering
or the exclusion query suffix is not working correctly).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

import os

from kalshi_bot_v10.vendor_clients import call_anthropic_haiku, call_groq_llama70b


def _call_judge(prompt: dict[str, str]) -> dict[str, Any]:
    """Call the cheapest available LLM as foreknowledge/anchoring judge.

    Preference: Haiku 4.5 (when ANTHROPIC_API_KEY set), else Groq Llama-3.3-70B.
    The judge task is binary classification (flagged true/false) which any
    competent LLM handles. Using Groq fallback keeps the foreknowledge audit
    functional even when Anthropic key is absent.
    """
    if os.environ.get("ANTHROPIC_API_KEY", ""):
        return call_anthropic_haiku(prompt)
    if os.environ.get("GROQ_API_KEY", ""):
        return call_groq_llama70b(prompt)
    return {"vendor": "none", "raw_text": "", "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "error": "no_judge_vendor"}

_JUDGE_SYSTEM = (
    "You are a content screening assistant. Your job is to flag search result"
    " snippets that could contaminate a forecaster's probability estimate."
    " You must respond ONLY with valid JSON."
)


def _build_judge_prompt(snippet: dict[str, Any], market_close_time: datetime) -> str:
    close_str = market_close_time.strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"Market close time: {close_str}\n\n"
        f"Snippet title: {snippet.get('title', '')}\n"
        f"Snippet date: {snippet.get('date', 'unknown')}\n"
        f"Snippet text:\n{snippet.get('snippet', '')}\n\n"
        "Does this snippet contain EITHER of the following:\n"
        "  (A) Any mention of Kalshi, Polymarket, Manifold, Metaculus, or any"
        " sportsbook prices, moneylines, odds, or contract prices?\n"
        "  (B) Information about the specific event outcome dated AFTER"
        f" {close_str}?\n\n"
        "Reply with JSON only:\n"
        "{\"flagged\": true|false, \"reason\": \"<short reason or empty string>\"}"
    )


def filter_snippets(
    snippets: list[dict[str, Any]],
    market_close_time: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Filter snippets through the Haiku 4.5 foreknowledge/price judge.

    Args:
        snippets: List of snippet dicts from tavily_search.search().
        market_close_time: The market's resolution time (UTC).

    Returns:
        (filtered_snippets, audit_log)

        filtered_snippets: snippets where judge returned flagged=False.
        audit_log: {
            "n_input": int,
            "n_filtered": int,
            "flag_reasons": [str, ...],
            "judge_errors": int,
            "warning": str or None,
        }
    """
    if not snippets:
        return [], {
            "n_input": 0,
            "n_filtered": 0,
            "flag_reasons": [],
            "judge_errors": 0,
            "warning": None,
        }

    kept: list[dict[str, Any]] = []
    flag_reasons: list[str] = []
    judge_errors = 0

    for snippet in snippets:
        user_text = _build_judge_prompt(snippet, market_close_time)
        prompt = {"system": _JUDGE_SYSTEM, "user": user_text}
        result = _call_judge(prompt)

        if result.get("error"):
            # On judge API error: keep the snippet (fail open; do not discard valid context)
            kept.append(snippet)
            judge_errors += 1
            continue

        raw = result.get("raw_text", "").strip()
        flagged = False
        reason = ""

        # Try to parse JSON from the response
        try:
            # Strip markdown code fences if present
            cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
            parsed = json.loads(cleaned)
            flagged = bool(parsed.get("flagged", False))
            reason = str(parsed.get("reason", ""))
        except (json.JSONDecodeError, TypeError):
            # If judge output is not parseable JSON, keep snippet (fail open)
            kept.append(snippet)
            judge_errors += 1
            continue

        if flagged:
            flag_reasons.append(reason)
        else:
            kept.append(snippet)

    n_input = len(snippets)
    n_filtered = n_input - len(kept)
    flag_rate = n_filtered / n_input if n_input > 0 else 0.0

    warning = None
    if flag_rate > 0.30:
        warning = (
            f"WARNING: {n_filtered}/{n_input} snippets flagged ({flag_rate:.0%})."
            " Judge may be over-aggressive or exclusion query filter is not working."
        )

    audit_log: dict[str, Any] = {
        "n_input": n_input,
        "n_filtered": n_filtered,
        "flag_reasons": flag_reasons,
        "judge_errors": judge_errors,
        "warning": warning,
    }

    return kept, audit_log
