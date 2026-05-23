"""Phase 1.5 smoke check: verify .env, RSA-PSS auth, and Kalshi reachability.

Run after generating Kalshi API keys and populating .env:

    uv run python -m scripts.phase_1_5.check_kalshi

Success path: prints "OK: Kalshi auth works" and exits 0.
Failure path: prints an actionable error and exits 1.

Common errors and what they mean:
  - "No Kalshi key_id configured" -> KALSHI_API_KEY_ID is empty in .env
  - "Kalshi private key not found" -> wrong KALSHI_PRIVATE_KEY_PATH
  - "Kalshi 401" -> key ID / signature mismatch (regenerate the key)
  - "Kalshi 429" -> rate limited; wait and retry
"""

from __future__ import annotations

import sys

import structlog

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient, KalshiHTTPError
from kalshi_bot.logging import configure_logging


def main() -> int:
    configure_logging()
    log = structlog.get_logger("check_kalshi")

    try:
        settings = load_settings()
    except Exception as exc:
        log.error("settings_load_failed", error=str(exc))
        print("\nFAIL: could not load .env. See error above.", file=sys.stderr)
        return 1

    log.info(
        "settings_loaded",
        env=settings.KALSHI_ENV,
        key_id_set=bool(settings.active_key_id),
        pem_path=str(settings.active_private_key_path),
    )

    try:
        with KalshiClient(settings) as client:
            status = client.ping()
            log.info("kalshi_exchange_status", **status)
    except KalshiHTTPError as http_err:
        log.error("kalshi_http_error", status=http_err.status, body=http_err.body[:300])
        print(
            f"\nFAIL: Kalshi returned HTTP {http_err.status}. "
            "If 401, double-check KALSHI_API_KEY_ID matches the key you generated "
            "and that KALSHI_PRIVATE_KEY_PATH points to the matching PEM. "
            "If you generated a READ-only key, that is correct for Phase 1.5.",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        log.error("kalshi_ping_failed", error=str(exc))
        print(f"\nFAIL: {exc}", file=sys.stderr)
        return 1

    print("\nOK: Kalshi auth works. .env is set up correctly. Ready for historical data pull.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
