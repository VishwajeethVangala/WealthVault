"""RFC 6238 time-based one-time passwords (HMAC-SHA1, 6 digits, 30s), standard library only."""

import base64
import hashlib
import hmac
import struct
import time
from typing import Optional


def generate_totp(secret: str, at: Optional[float] = None, digits: int = 6, step: int = 30) -> str:
    """Return the TOTP code for a base32 secret (spaces and case are ignored)."""
    cleaned = "".join(secret.split()).upper()
    cleaned += "=" * (-len(cleaned) % 8)
    key = base64.b32decode(cleaned, casefold=True)
    counter = int((time.time() if at is None else at) // step)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)
