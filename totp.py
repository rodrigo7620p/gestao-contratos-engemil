from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code(secret: str, timestamp: int | None = None, interval: int = 30) -> str:
    timestamp = int(timestamp or time.time())
    counter = timestamp // interval
    padded = secret.upper() + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def verify(secret: str, token: str, window: int = 2) -> bool:
    token = "".join(ch for ch in str(token) if ch.isdigit())
    now = int(time.time())
    return len(token) == 6 and any(
        hmac.compare_digest(code(secret, now + shift * 30), token)
        for shift in range(-window, window + 1)
    )


def provisioning_uri(secret: str, email: str, issuer: str = "ENGEMIL Gestão Contratual") -> str:
    label = quote(f"{issuer}:{email}")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
        "&algorithm=SHA1&digits=6&period=30"
    )
