"""Security primitives: password hashing, JWT, RBAC dependencies."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from passlib.context import CryptContext

from fmp.core.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str | int, extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def get_current_user_from_query(token: str) -> dict[str, Any] | None:
    """Decode a JWT for WebSocket upgrade handshakes (no DB round-trip).

    Returns the token claims on success or ``None`` on any invalid/garbage
    token so callers can close the socket with a 4401 policy violation.
    """
    try:
        return decode_token(token)
    except jwt.PyJWTError:
        return None


def generate_secure_code(length: int = 8) -> str:
    """Cryptographically secure numeric code with uniform digit distribution.

    ``secrets.randbelow`` performs internal rejection sampling, so there is
    no modulo bias per digit.
    """
    if length < 4:
        raise ValueError("code length must be >= 4")
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def hash_code(code: str) -> str:
    """SHA-256 + random salt; codes are never stored in plaintext."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", code.encode(), salt.encode(), iterations=120_000
    )
    return f"{salt}${digest.hex()}"


def verify_code(code: str, stored: str) -> bool:
    try:
        salt, digest_hex = stored.split("$")
    except ValueError:
        return False
    computed = hashlib.pbkdf2_hmac(
        "sha256", code.encode(), salt.encode(), iterations=120_000
    ).hex()
    return hmac.compare_digest(computed, digest_hex)


def code_fingerprint(code: str) -> str:
    """Deterministic HMAC-SHA256 fingerprint of a code.

    Used ONLY for O(log N) indexed lookups and the Redis "consumed" set.
    It does not reveal the code and, unlike PBKDF2, is repeatable across
    calls so Redis/DB indexes stay usable. The at-rest secret remains the
    salted ``hash_code``.
    """
    return hmac.new(
        settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256
    ).hexdigest()