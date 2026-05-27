"""Encrypt API keys at rest on the Mac backend (never sent to frontend)."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_KEY_FILE = _BASE / "data" / ".jarvis_key"


def _fernet():
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return None
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _KEY_FILE.exists():
        _KEY_FILE.write_bytes(Fernet.generate_key())
    key = _KEY_FILE.read_bytes().strip()
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    f = _fernet()
    if not f:
        return "b64:" + base64.urlsafe_b64encode(value.encode()).decode()
    return "enc:" + f.encrypt(value.encode()).decode()


def decrypt_secret(stored: str) -> str:
    if not stored:
        return ""
    if stored.startswith("enc:"):
        f = _fernet()
        if not f:
            return ""
        try:
            return f.decrypt(stored[4:].encode()).decode()
        except Exception:
            return ""
    if stored.startswith("b64:"):
        try:
            return base64.urlsafe_b64decode(stored[4:].encode()).decode()
        except Exception:
            return ""
    return stored


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "••••"
    return value[:4] + "••••" + value[-4:]
