"""Tests for Kalshi RSA-PSS signing.

We generate an ephemeral RSA keypair per test rather than checking in a
fixture private key. The point is to verify the protocol implementation
(signature input string, padding, header names), not a specific vendor key.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from kalshi_bot.data import auth

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def test_request_path_strips_query_string() -> None:
    url = "https://external-api.kalshi.com/trade-api/v2/portfolio/orders?limit=5&cursor=abc"
    assert auth.request_path(url) == "/trade-api/v2/portfolio/orders"


def test_request_path_handles_no_query() -> None:
    url = "https://external-api.kalshi.com/trade-api/v2/markets"
    assert auth.request_path(url) == "/trade-api/v2/markets"


def test_sign_returns_deterministic_timestamp_string(
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    private, _ = keypair
    ts_str, _ = auth.sign(private, "GET", "/trade-api/v2/markets", timestamp_ms=1747938400000)
    assert ts_str == "1747938400000"


def test_sign_uppercases_method(
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    """Signature for method='get' should match signature for method='GET'.

    Kalshi spec is uppercase method; the function normalizes for us.
    """
    private, public = keypair
    ts = 1700000000000
    _, sig_lower = auth.sign(private, "get", "/trade-api/v2/markets", timestamp_ms=ts)
    _, sig_upper = auth.sign(private, "GET", "/trade-api/v2/markets", timestamp_ms=ts)
    # PSS is randomized so signatures differ byte-for-byte but both verify
    # against the same canonical message. We re-derive the message and check.
    canonical = ("1700000000000" + "GET" + "/trade-api/v2/markets").encode("utf-8")
    for sig_b64 in (sig_lower, sig_upper):
        sig = base64.b64decode(sig_b64)
        public.verify(
            sig,
            canonical,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=hashes.SHA256.digest_size,
            ),
            hashes.SHA256(),
        )


def test_sign_signature_verifies_with_public_key(
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    private, public = keypair
    ts_str, sig_b64 = auth.sign(
        private, "POST", "/trade-api/v2/portfolio/orders", timestamp_ms=1747938400123
    )
    message = (ts_str + "POST" + "/trade-api/v2/portfolio/orders").encode("utf-8")
    public.verify(
        base64.b64decode(sig_b64),
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=hashes.SHA256.digest_size,
        ),
        hashes.SHA256(),
    )


def test_build_headers_shape(
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    private, _ = keypair
    headers = auth.build_headers(
        private, "key-123", "GET", "/trade-api/v2/markets", timestamp_ms=1747938400000
    )
    assert set(headers) == {
        "KALSHI-ACCESS-KEY",
        "KALSHI-ACCESS-TIMESTAMP",
        "KALSHI-ACCESS-SIGNATURE",
    }
    assert headers["KALSHI-ACCESS-KEY"] == "key-123"
    assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1747938400000"
    assert headers["KALSHI-ACCESS-SIGNATURE"]


def test_load_private_key_raises_on_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.pem"
    with pytest.raises(FileNotFoundError):
        auth.load_private_key(missing)


def test_load_private_key_roundtrip(tmp_path: Path) -> None:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_bytes = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pem_path = tmp_path / "key.pem"
    pem_path.write_bytes(pem_bytes)

    loaded = auth.load_private_key(pem_path)
    assert loaded.key_size == private.key_size
