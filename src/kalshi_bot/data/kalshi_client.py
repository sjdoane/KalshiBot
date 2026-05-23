"""Sync HTTP client for the Kalshi v2 REST API.

Wraps `httpx` with RSA-PSS signing per request and exponential backoff on
429 (token-bucket overage). Designed for Phase 1.5 read-only historical
data pulls; the same client will back the live bot in later phases, with
trading endpoints added via the same `_request` plumbing.

Endpoint conventions: callers pass the path RELATIVE to the API version
prefix. For example `client.get("/markets")` requests
`/trade-api/v2/markets`. The full path (with prefix) is what gets signed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from kalshi_bot.data import auth

if TYPE_CHECKING:
    from collections.abc import Iterator

    from kalshi_bot.config import Settings

log = structlog.get_logger(__name__)


class KalshiRateLimitedError(Exception):
    """Raised on HTTP 429 from Kalshi to trigger tenacity's backoff."""


class KalshiHTTPError(Exception):
    """Raised on non-429 HTTP errors. Carries status code and body excerpt."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"Kalshi {status}: {body[:200]}")


class KalshiClient:
    """Sync Kalshi v2 REST client with RSA-PSS auth.

    Use as a context manager so the underlying httpx.Client closes cleanly.
    Instances are not thread-safe; create one per worker if you parallelize.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.active_key_id:
            raise ValueError(
                f"No Kalshi key_id configured for env={settings.KALSHI_ENV}. "
                "Set KALSHI_API_KEY_ID (or KALSHI_DEMO_API_KEY_ID) in .env."
            )
        pem_path = settings.active_private_key_path
        if not pem_path or not pem_path.exists():
            raise ValueError(
                f"Kalshi private key not found at {pem_path!s}. "
                "Set KALSHI_PRIVATE_KEY_PATH in .env (absolute path outside the repo)."
            )

        self._key_id = settings.active_key_id
        self._private_key = auth.load_private_key(pem_path)

        base = urlsplit(settings.kalshi_base_url)
        self._host = f"{base.scheme}://{base.netloc}"
        self._prefix = base.path  # e.g. "/trade-api/v2"

        self._client = httpx.Client(timeout=30.0)
        self._env = settings.KALSHI_ENV
        log.info("kalshi_client_init", env=self._env, host=self._host)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> KalshiClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @retry(
        retry=retry_if_exception_type(KalshiRateLimitedError),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(8),
        reraise=True,
    )
    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = self._prefix + endpoint
        url = self._host + path
        headers = auth.build_headers(self._private_key, self._key_id, method, path)
        response = self._client.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json,
        )
        if response.status_code == 429:
            log.warning("kalshi_rate_limited", path=path)
            raise KalshiRateLimitedError()
        if response.status_code >= 400:
            raise KalshiHTTPError(response.status_code, response.text)
        return response.json()

    def get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        return self._request("GET", endpoint, params=params or None)

    def post(self, endpoint: str, json: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", endpoint, json=json)

    def paginate(
        self,
        endpoint: str,
        *,
        item_key: str,
        limit: int = 100,
        max_pages: int | None = None,
        **params: Any,
    ) -> Iterator[dict[str, Any]]:
        """Yield items across all pages of a cursor-paginated endpoint.

        Kalshi `/markets`, `/historical/trades`, etc. return shapes like
        `{"<item_key>": [...], "cursor": "..."}`. Pass `item_key` to pull
        the right list ("markets", "trades", "fills", ...).

        max_pages caps the walk in case the cursor never terminates; pass
        None for "drain the entire endpoint" (used for historical pulls).
        """
        cursor: str | None = None
        page = 0
        request_params: dict[str, Any] = dict(params)
        request_params["limit"] = limit
        while True:
            page += 1
            if cursor:
                request_params["cursor"] = cursor
            payload = self.get(endpoint, **request_params)
            items: list[dict[str, Any]] = payload.get(item_key, []) or []
            yield from items
            cursor = payload.get("cursor")
            if not cursor or not items:
                log.info(
                    "kalshi_paginate_done",
                    endpoint=endpoint,
                    pages=page,
                )
                return
            if max_pages is not None and page >= max_pages:
                log.info(
                    "kalshi_paginate_max_pages",
                    endpoint=endpoint,
                    pages=page,
                    max_pages=max_pages,
                )
                return

    def ping(self) -> dict[str, Any]:
        """Smoke test: hit `/exchange/status` to verify auth + connectivity."""
        return self.get("/exchange/status")
