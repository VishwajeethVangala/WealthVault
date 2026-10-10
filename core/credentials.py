"""Encryption helpers for per-user broker credentials.

Broker secrets (API keys, PINs, TOTP seeds, session tokens) are encrypted with a Fernet
key from settings before being written to Azure Table Storage, and decrypted only inside
the backend. They are never returned to the browser.
"""

import json
from typing import Any, Dict

from cryptography.fernet import Fernet, InvalidToken

from core.config import get_settings


class CredentialStoreError(Exception):
    """Raised when credentials cannot be encrypted or decrypted."""


def _fernet() -> Fernet:
    key = get_settings().CREDENTIAL_ENCRYPTION_KEY.strip()
    if not key:
        raise CredentialStoreError(
            "CREDENTIAL_ENCRYPTION_KEY is not configured. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" '
            "and add it to .env."
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise CredentialStoreError(f"CREDENTIAL_ENCRYPTION_KEY is not a valid Fernet key: {exc}") from exc


def encrypt_json(data: Dict[str, Any]) -> str:
    """Encrypt a JSON-serializable dict into an opaque token string."""
    return _fernet().encrypt(json.dumps(data).encode("utf-8")).decode("ascii")


def decrypt_json(token: str) -> Dict[str, Any]:
    """Decrypt a token produced by encrypt_json."""
    try:
        return json.loads(_fernet().decrypt(token.encode("ascii")).decode("utf-8"))
    except InvalidToken as exc:
        raise CredentialStoreError(
            "Stored credentials cannot be decrypted (the encryption key changed). Re-enter them."
        ) from exc
