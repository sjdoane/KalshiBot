"""Thin HTTP wrappers for each LLM vendor used in V10-B.

Each function accepts a prompt dict with keys:
    "system": str   -- system prompt text (same for all vendors)
    "user": str     -- per-market user prompt (unique per forecast)

And returns a dict:
    "vendor": str
    "raw_text": str       -- raw completion text (JSON expected)
    "tokens_in": int
    "tokens_out": int
    "cost_usd": float
    "error": str | None   -- None on success; error message on failure

On error: error field is populated, NOT raised as exception.
Callers skip vendors where error is not None.

Cost estimates (2026-05 pricing):
    Anthropic Haiku 4.5:  $0.00025/1k in + $0.00125/1k out
    Anthropic Opus 4.7:   $0.015/1k in   + $0.075/1k out
    Gemini 2.5 Flash:     free tier (0 cost up to 1500 req/day)
    DeepSeek V4 Flash:    $0.00014/1k in + $0.00028/1k out (5M free tokens initially)
    Groq Llama-3.1-70B:   free tier (0 cost up to 1000 req/day)
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Pricing constants (USD per 1k tokens)
# ---------------------------------------------------------------------------

_HAIKU_COST_IN = 0.00025   # per 1k input tokens
_HAIKU_COST_OUT = 0.00125  # per 1k output tokens
_OPUS_COST_IN = 0.015
_OPUS_COST_OUT = 0.075
_DEEPSEEK_COST_IN = 0.00014
_DEEPSEEK_COST_OUT = 0.00028
# Gemini and Groq: free tier; record $0
_GEMINI_COST_IN = 0.0
_GEMINI_COST_OUT = 0.0
_GROQ_COST_IN = 0.0
_GROQ_COST_OUT = 0.0

_ANTHROPIC_BASE = "https://api.anthropic.com/v1"
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
_DEEPSEEK_BASE = "https://api.deepseek.com/v1"
_GROQ_BASE = "https://api.groq.com/openai/v1"

_TIMEOUT = 60  # seconds

# Per-vendor rate limiting (free tier caps as of May 2026)
# Gemini 2.5 Flash: 15 RPM free tier -> ~4.0s between calls
# Groq Llama 3.3: 30 RPM free tier -> ~2.0s between calls
import time as _time
import threading as _threading
_VENDOR_LAST_CALL: dict[str, float] = {}
_VENDOR_MIN_SPACING: dict[str, float] = {
    "gemini-2.5-flash": 4.2,
    "groq-llama-3.3-70b": 2.1,
}
_RATE_LOCK = _threading.Lock()


def _rate_limit(vendor: str) -> None:
    """Block until min spacing since last call for this vendor is satisfied."""
    spacing = _VENDOR_MIN_SPACING.get(vendor, 0.0)
    if spacing <= 0:
        return
    with _RATE_LOCK:
        now = _time.monotonic()
        last = _VENDOR_LAST_CALL.get(vendor, 0.0)
        wait = (last + spacing) - now
        if wait > 0:
            _time.sleep(wait)
        _VENDOR_LAST_CALL[vendor] = _time.monotonic()


def _empty_response(vendor: str, error: str) -> dict[str, Any]:
    return {
        "vendor": vendor,
        "raw_text": "",
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "error": error,
    }


def _call_anthropic(
    model: str,
    prompt: dict[str, str],
    cost_per_in: float,
    cost_per_out: float,
    max_tokens: int = 512,
) -> dict[str, Any]:
    """Shared Anthropic Messages API caller."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _empty_response(model, "ANTHROPIC_API_KEY not set")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": prompt.get("system", ""),
        "messages": [{"role": "user", "content": prompt.get("user", "")}],
    }

    try:
        resp = requests.post(
            f"{_ANTHROPIC_BASE}/messages",
            headers=headers,
            json=body,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        return _empty_response(model, f"HTTP error: {exc}")
    except json.JSONDecodeError as exc:
        return _empty_response(model, f"JSON decode error: {exc}")

    try:
        raw_text = data["content"][0]["text"]
        tokens_in = data["usage"]["input_tokens"]
        tokens_out = data["usage"]["output_tokens"]
        cost = (tokens_in / 1000) * cost_per_in + (tokens_out / 1000) * cost_per_out
        return {
            "vendor": model,
            "raw_text": raw_text,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": round(cost, 6),
            "error": None,
        }
    except (KeyError, IndexError, TypeError) as exc:
        return _empty_response(model, f"Response parse error: {exc}")


def call_anthropic_opus(prompt: dict[str, str], tools: list | None = None) -> dict[str, Any]:
    """Claude Opus 4.7 -- supervisor pass only. Tools param reserved for future use."""
    # tools param is accepted for API compatibility but not wired (supervisor role only)
    return _call_anthropic(
        "claude-opus-4-5",
        prompt,
        _OPUS_COST_IN,
        _OPUS_COST_OUT,
        max_tokens=1024,
    )


def call_anthropic_haiku(prompt: dict[str, str], max_tokens: int = 1024) -> dict[str, Any]:
    """Claude Haiku 4.5 -- forecaster sub-agent OR foreknowledge/anchoring judge.

    max_tokens default 1024 to give the forecaster sub-agent room for reasoning
    before the JSON p_yes emission. Judge calls (shorter outputs) can pass 256.
    """
    return _call_anthropic(
        "claude-haiku-4-5",
        prompt,
        _HAIKU_COST_IN,
        _HAIKU_COST_OUT,
        max_tokens=max_tokens,
    )


def call_gemini_flash(prompt: dict[str, str]) -> dict[str, Any]:
    """Google Gemini 2.5 Flash via REST (free tier)."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return _empty_response("gemini-2.5-flash", "GEMINI_API_KEY not set")

    model_id = "gemini-2.5-flash"
    url = f"{_GEMINI_BASE}/models/{model_id}:generateContent?key={api_key}"
    system_text = prompt.get("system", "")
    user_text = prompt.get("user", "")

    body: dict[str, Any] = {
        "system_instruction": {"parts": [{"text": system_text}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {
            "maxOutputTokens": 2048,
            "temperature": 0.0,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }

    _rate_limit("gemini-2.5-flash")
    try:
        resp = requests.post(url, json=body, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        return _empty_response("gemini-2.5-flash", f"HTTP error: {exc}")
    except json.JSONDecodeError as exc:
        return _empty_response("gemini-2.5-flash", f"JSON decode error: {exc}")

    try:
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        # Gemini does not always return usage; default to 0
        usage = data.get("usageMetadata", {})
        tokens_in = usage.get("promptTokenCount", 0)
        tokens_out = usage.get("candidatesTokenCount", 0)
        return {
            "vendor": "gemini-2.5-flash",
            "raw_text": raw_text,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": 0.0,
            "error": None,
        }
    except (KeyError, IndexError, TypeError) as exc:
        return _empty_response("gemini-2.5-flash", f"Response parse error: {exc}")


def _call_openai_compat(
    vendor: str,
    base_url: str,
    api_key: str,
    model: str,
    prompt: dict[str, str],
    cost_per_in: float,
    cost_per_out: float,
    max_tokens: int = 512,
) -> dict[str, Any]:
    """Shared caller for OpenAI-compatible endpoints (DeepSeek, Groq)."""
    if not api_key:
        return _empty_response(vendor, f"API key not set for {vendor}")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt.get("system", "")},
            {"role": "user", "content": prompt.get("user", "")},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=body,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        return _empty_response(vendor, f"HTTP error: {exc}")
    except json.JSONDecodeError as exc:
        return _empty_response(vendor, f"JSON decode error: {exc}")

    try:
        raw_text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        cost = (tokens_in / 1000) * cost_per_in + (tokens_out / 1000) * cost_per_out
        return {
            "vendor": vendor,
            "raw_text": raw_text,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": round(cost, 6),
            "error": None,
        }
    except (KeyError, IndexError, TypeError) as exc:
        return _empty_response(vendor, f"Response parse error: {exc}")


def call_deepseek_flash(prompt: dict[str, str]) -> dict[str, Any]:
    """DeepSeek V4 Flash via OpenAI-compatible endpoint at api.deepseek.com/v1."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    return _call_openai_compat(
        vendor="deepseek-chat",
        base_url=_DEEPSEEK_BASE,
        api_key=api_key,
        model="deepseek-chat",
        prompt=prompt,
        cost_per_in=_DEEPSEEK_COST_IN,
        cost_per_out=_DEEPSEEK_COST_OUT,
    )


def call_groq_llama70b(prompt: dict[str, str]) -> dict[str, Any]:
    """Groq Llama-3.3-70B via OpenAI-compatible endpoint at api.groq.com/openai/v1."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    _rate_limit("groq-llama-3.3-70b")
    return _call_openai_compat(
        vendor="groq-llama-3.3-70b",
        base_url=_GROQ_BASE,
        api_key=api_key,
        model="llama-3.3-70b-versatile",
        prompt=prompt,
        cost_per_in=_GROQ_COST_IN,
        cost_per_out=_GROQ_COST_OUT,
    )
