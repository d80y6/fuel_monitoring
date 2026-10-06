"""Security primitives: password hashing, JWT, RBAC dependencies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
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
    now = datetime.now(UTC)
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


def create_refresh_token(subject: str | int) -> str:
    """Mint a longer-lived refresh token bound to the same subject.

    Issued with ``typ=refresh``; ``decode_token`` rejects such tokens so a
    refresh token can never be accepted as an access token, and the refresh
    path can distinguish it from an access token.
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "jti": uuid.uuid4().hex,
        "iss": TOKEN_ISSUER,
        "aud": TOKEN_AUDIENCE,
        "typ": "refresh",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Strictly decode+verify a token as a refresh token (``typ=refresh``).

    Requires ``typ`` in addition to the access-token claim set; access tokens,
    wrong-audience/issuer tokens, tampered or expired tokens all raise
    ``jwt.PyJWTError``.
    """
    claims = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        audience=TOKEN_AUDIENCE,
        issuer=TOKEN_ISSUER,
        options={"require": ["exp", "iat", "iss", "aud", "sub", "typ"]},
    )
    if claims.get("typ") != "refresh":
        raise jwt.InvalidTokenError("token is not a refresh token")
    return claims


def decode_token(token: str) -> dict[str, Any]:
    """Strictly decode+verify a JWT, explicitly rejecting refresh tokens.

    Requires and validates exp/iat/iss/aud/sub and the HS256 signature, so
    tokens minted by other services (wrong ``aud``/``iss``) are rejected.
    Long-lived ``typ=refresh`` tokens are rejected outright so they can never
    be accepted where an access token is required.
    """
    claims = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        audience=TOKEN_AUDIENCE,
        issuer=TOKEN_ISSUER,
        options={"require": ["exp", "iat", "iss", "aud", "sub"]},
    )
    if claims.get("typ") == "refresh":
        raise jwt.InvalidTokenError("refresh token used as access token")
    return claims


#: Bounded in-process fallback revocation denylist (jti -> exp epoch) for when
#: Redis is unreachable, mirroring the login rate-limiter fallback so a revoked
#: token is never silently re-accepted. Assumes a single-process deployment.
_REVOKED_MAX_KEYS = 100_000
_revoked_jtis: dict[str, int] = {}


async def revoke_token(redis, claims: dict[str, Any]) -> None:
    """Denylist the token's ``jti`` for its remaining lifetime (exp - now).

    Redis holds the denylist when available; on outage the jti is recorded in a
    bounded in-process dict so revocation never fails open.
    """
    jti = claims.get("jti")
    exp = claims.get("exp")
    if not isinstance(jti, str) or not isinstance(exp, int):
        return
    ttl = max(1, exp - int(time.time()))
    try:
        await redis.revoke_jwt(jti, ttl)
        return
    except Exception:
        pass
    _revoked_jtis[jti] = exp
    while len(_revoked_jtis) > _REVOKED_MAX_KEYS:
        _revoked_jtis.pop(next(iter(_revoked_jtis)))


async def token_revoked(redis, claims: dict[str, Any]) -> bool:
    """True when the token's ``jti`` has been revoked (Redis or fallback)."""
    jti = claims.get("jti")
    exp = claims.get("exp")
    if not isinstance(jti, str):
        return False
    try:
        if await redis.jwt_revoked(jti):
            return True
    except Exception:
        pass
    return isinstance(exp, int) and _revoked_jtis.get(jti, -1) > int(time.time())


async def claim_token(redis, claims: dict[str, Any]) -> bool:
    """Atomically revoke the token, winning exactly one racer.

    Combines the revocation check and write into a single atomic ``SET NX`` so
    concurrent rotation of the same refresh token cannot both succeed: the first
    caller claims the jti (returns True) and any later caller sees it already
    revoked (returns False). Falls back to a process-local claim on Redis outage.
    """
    jti = claims.get("jti")
    exp = claims.get("exp")
    if not isinstance(jti, str) or not isinstance(exp, int):
        return False
    ttl = max(1, exp - int(time.time()))
    try:
        return bool(await redis.claim_revocation(jti, ttl))
    except Exception:
        pass
    if jti in _revoked_jtis and _revoked_jtis[jti] > int(time.time()):
        return False
    _revoked_jtis[jti] = exp
    while len(_revoked_jtis) > _REVOKED_MAX_KEYS:
        _revoked_jtis.pop(next(iter(_revoked_jtis)))
    return True


def validate_password_complexity(plain: str) -> list[str]:
    """Return password-policy violation messages; empty list means acceptable.

    Policy: minimum length (``PASSWORD_MIN_LENGTH``) plus at least 3 of the 4
    character classes (lowercase, uppercase, digit, symbol).
    """
    violations: list[str] = []
    if len(plain) < settings.PASSWORD_MIN_LENGTH:
        violations.append(f"must be at least {settings.PASSWORD_MIN_LENGTH} characters")
    class_present = sum(
        (
            any(c.islower() for c in plain),
            any(c.isupper() for c in plain),
            any(c.isdigit() for c in plain),
            any(not c.isalnum() for c in plain),
        )
    )
    if class_present < 3:
        violations.append(
            "must include at least 3 of: lowercase, uppercase, digit, symbol"
        )
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
