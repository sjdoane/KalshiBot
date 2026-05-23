"""Kalshi RSA-PSS request signing.

Per Kalshi docs: every authenticated request carries three headers.

    KALSHI-ACCESS-KEY:        public Key ID returned at key creation
    KALSHI-ACCESS-TIMESTAMP:  Unix epoch in milliseconds (NOT seconds)
    KALSHI-ACCESS-SIGNATURE:  base64(RSA_PSS_SHA256(timestamp_ms + METHOD + path))

The signature input is the timestamp string concatenated with the uppercase
HTTP method and the request path with the query string stripped. RSA-PSS
uses MGF1+SHA256 with salt length equal to the digest length (32 bytes).

Reference: https://docs.kalshi.com/getting_started/api_keys
"""

from __future__ import annotations

import base64
import time
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

if TYPE_CHECKING:
    from pathlib import Path


def load_private_key(pem_path: Path) -> RSAPrivateKey:
    """Load an unencrypted RSA private key from a PEM file.

    Raises FileNotFoundError if pem_path does not exist, and TypeError if the
    file contains a non-RSA key. We do not support encrypted PEMs here; if
    the operator wants passphrase-protected keys later, this becomes a
    config knob.
    """
    if not pem_path.exists():
        raise FileNotFoundError(f"Kalshi private key not found at {pem_path}")
    pem_bytes = pem_path.read_bytes()
    key = serialization.load_pem_private_key(pem_bytes, password=None)
    if not isinstance(key, RSAPrivateKey):
        raise TypeError(
            f"Expected RSA private key in {pem_path}, got {type(key).__name__}"
        )
    return key


def request_path(url: str) -> str:
    """Return the path component of a URL, excluding scheme/host/query/fragment.

    Kalshi signs the path WITHOUT the query string. urlsplit().path gives us
    exactly that. For a URL like "https://external-api.kalshi.com/trade-api/
    v2/portfolio/orders?limit=5" this returns "/trade-api/v2/portfolio/orders".
    """
    return urlsplit(url).path


def sign(
    private_key: RSAPrivateKey,
    method: str,
    path: str,
    timestamp_ms: int | None = None,
) -> tuple[str, str]:
    """Sign a Kalshi request and return (timestamp_ms_str, base64_signature).

    The caller passes the request method and path; this function does NOT
    parse a URL because callers may be working with httpx Request objects
    that already split URL components. If you have a full URL, run it
    through `request_path()` first.

    timestamp_ms is taken as input to make signatures reproducible in tests;
    in production callers pass None and we use the wall clock.
    """
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)
    ts = str(timestamp_ms)
    message = (ts + method.upper() + path).encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=hashes.SHA256.digest_size,
        ),
        hashes.SHA256(),
    )
    return ts, base64.b64encode(signature).decode("ascii")


def build_headers(
    private_key: RSAPrivateKey,
    key_id: str,
    method: str,
    path: str,
    timestamp_ms: int | None = None,
) -> dict[str, str]:
    """Build the full set of Kalshi auth headers for one request."""
    ts, sig = sign(private_key, method, path, timestamp_ms)
    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": sig,
    }
