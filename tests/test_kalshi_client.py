"""Unit tests for KalshiClient using httpx MockTransport.

Real-keys integration smoke tests live in scripts/phase_1_5/check_kalshi.py
and require .env to be populated; this file covers protocol-correctness
behaviors that should work without any network.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi_bot.config import Settings
from kalshi_bot.data import auth
from kalshi_bot.data.kalshi_client import (
    KalshiClient,
    KalshiHTTPError,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def fake_pem(tmp_path: Path) -> Path:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    p = tmp_path / "kalshi.pem"
    p.write_bytes(pem)
    return p


@pytest.fixture
def settings(fake_pem: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    # pydantic-settings reads .env automatically; explicitly point env vars
    # so the test does not depend on the dev machine's .env file.
    monkeypatch.setenv("KALSHI_ENV", "demo")
    monkeypatch.setenv("KALSHI_DEMO_API_KEY_ID", "test-key-id")
    monkeypatch.setenv("KALSHI_DEMO_PRIVATE_KEY_PATH", str(fake_pem))
    monkeypatch.setenv("KALSHI_API_KEY_ID", "")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", "")
    return Settings()


def _install_mock(client: KalshiClient, handler) -> None:
    """Replace the internal httpx.Client with one backed by MockTransport."""
    client._client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


def test_request_includes_auth_headers(settings: Settings) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        for k, v in request.headers.items():
            if k.upper().startswith("KALSHI-"):
                seen[k.upper()] = v
        return httpx.Response(200, json={"markets": [], "cursor": ""})

    with KalshiClient(settings) as client:
        _install_mock(client, handler)
        client.get("/markets")

    assert "KALSHI-ACCESS-KEY" in seen
    assert "KALSHI-ACCESS-TIMESTAMP" in seen
    assert "KALSHI-ACCESS-SIGNATURE" in seen
    assert seen["KALSHI-ACCESS-KEY"] == "test-key-id"


def test_signs_path_without_query_string(settings: Settings, fake_pem: Path) -> None:
    """Verify the signature is over the path with NO query string, even when
    the caller passes ?params."""
    captured_ts: list[str] = []
    captured_sig: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_ts.append(request.headers["KALSHI-ACCESS-TIMESTAMP"])
        captured_sig.append(request.headers["KALSHI-ACCESS-SIGNATURE"])
        return httpx.Response(200, json={"markets": [], "cursor": ""})

    with KalshiClient(settings) as client:
        _install_mock(client, handler)
        client.get("/markets", limit=50, status="open")

    # Reproduce the signature; if the client signed the path with the query
    # string baked in, this verification would fail.
    private = auth.load_private_key(fake_pem)
    ts, sig = auth.sign(
        private,
        "GET",
        "/trade-api/v2/markets",
        timestamp_ms=int(captured_ts[0]),
    )
    # PSS signatures are randomized, so we cannot byte-compare. Instead,
    # verify the captured signature against the canonical message.
    from base64 import b64decode

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    message = (captured_ts[0] + "GET" + "/trade-api/v2/markets").encode()
    private.public_key().verify(
        b64decode(captured_sig[0]),
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=hashes.SHA256.digest_size,
        ),
        hashes.SHA256(),
    )


def test_retries_on_429_then_succeeds(settings: Settings) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"error": "too many requests"})
        return httpx.Response(200, json={"markets": [{"ticker": "KXHIGHNY-X"}], "cursor": ""})

    with KalshiClient(settings) as client:
        _install_mock(client, handler)
        out = client.get("/markets")

    assert calls["n"] == 3
    assert out["markets"][0]["ticker"] == "KXHIGHNY-X"


def test_raises_on_4xx_other_than_429(settings: Settings) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, content=b'{"error":"unauthorized"}')

    with KalshiClient(settings) as client:
        _install_mock(client, handler)
        with pytest.raises(KalshiHTTPError) as exc_info:
            client.get("/markets")

    assert exc_info.value.status == 401


def test_paginate_drains_all_pages(settings: Settings) -> None:
    pages = [
        {"markets": [{"ticker": "A"}, {"ticker": "B"}], "cursor": "p2"},
        {"markets": [{"ticker": "C"}], "cursor": "p3"},
        {"markets": [], "cursor": ""},
    ]
    seen_cursors: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        seen_cursors.append(cursor)
        return httpx.Response(200, json=pages.pop(0))

    with KalshiClient(settings) as client:
        _install_mock(client, handler)
        tickers = [m["ticker"] for m in client.paginate("/markets", item_key="markets")]

    assert tickers == ["A", "B", "C"]
    # First request has no cursor; subsequent ones carry the previous cursor
    assert seen_cursors[0] is None
    assert seen_cursors[1] == "p2"


def test_paginate_respects_max_pages(settings: Settings) -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json={"markets": [{"ticker": f"M{calls['n']}"}], "cursor": "more"},
        )

    with KalshiClient(settings) as client:
        _install_mock(client, handler)
        items = list(client.paginate("/markets", item_key="markets", max_pages=3))

    assert len(items) == 3
    assert calls["n"] == 3
