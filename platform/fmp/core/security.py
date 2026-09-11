"""Security primitives: password hashing, JWT, RBAC dependencies."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from fmp.core.config import get_settings

settings = get_settings()

# JWT issuer/audience: prevents token confusion across services/contexts (C1).
TOKEN_ISSUER = "fuel-platform"
TOKEN_AUDIENCE = "fuel-platform-api"

# OWASP-recommended PBKDF2-SHA256 cost for interactive login as of 2023.
PBKDF2_ITERATIONS = 210_000
_SALT_BYTES = 16
_HASH_BYTES = 32


def hash_password(plain: str) -> str:
    """PBKDF2-SHA256 password hash; format ``$pbkdf2-sha256$<iter>$<saltB64>$<dkB64>``.

    Designed to verify identically to legacy bcrypt hashes via a separate
    reader; new accounts always use PBKDF2. Stdlib-only (no bcrypt C binding).
    """
    salt = os.urandom(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(
        "sha256", plain.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=_HASH_BYTES
    )
    return "$pbkdf2-sha256${0}${1}${2}".format(
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(dk).decode("ascii"),
    )


def verify_password(plain: str, stored: str) -> bool:
    parts = stored.split("$")
    if len(parts) != 5 or parts[1] != "pbkdf2-sha256":
        return False
    try:
        iterations = int(parts[2])
        salt = base64.b64decode(parts[3])
        expected = base64.b64decode(parts[4])
    except (ValueError, TypeError):
        return False
    dk = hashlib.pbkdf2_hmac(
        "sha256", plain.encode("utf-8"), salt, iterations, dklen=len(expected)
    )
    return hmac.compare_digest(dk, expected)


def create_access_token(subject: str | int, extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": uuid.uuid4().hex,
        "iss": TOKEN_ISSUER,
        "aud": TOKEN_AUDIENCE,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Strictly decode+verify a JWT.

    Requires and validates exp/iat/iss/aud/sub and the HS256 signature, so
    tokens minted by other services (wrong ``aud``/``iss``) are rejected.
    """
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        audience=TOKEN_AUDIENCE,
        issuer=TOKEN_ISSUER,
        options={"require": ["exp", "iat", "iss", "aud", "sub"]},
    )


def validate_password_complexity(plain: str) -> list[str]:
    """Return password-policy violation messages; empty list means acceptable.

    Policy: minimum length (``PASSWORD_MIN_LENGTH``) plus at least 3 of the 4
    character classes (lowercase, uppercase, digit, symbol).
    """
    violations: list[str] = []
    if len(plain) < settings.PASSWORD_MIN_LENGTH:
        violations.append(f"must be at least {settings.PASSWORD_MIN_LENGTH} characters")
    class_present = sum((
        any(c.islower() for c in plain),
        any(c.isupper() for c in plain),
        any(c.isdigit() for c in plain),
        any(not c.isalnum() for c in plain),
    ))
    if class_present < 3:
        violations.append("must include at least 3 of: lowercase, uppercase, digit, symbol")
    return violations


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