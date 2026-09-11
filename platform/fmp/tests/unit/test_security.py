"""Unit tests for JWT hardening (C1) and password complexity (H4)."""
from __future__ import annotations

import pytest
import jwt

from fmp.core.security import (
    TOKEN_AUDIENCE,
    TOKEN_ISSUER,
    create_access_token,
    decode_token,
    settings,
    validate_password_complexity,
)


def _raw_claims(token: str) -> dict:
    """Decode WITHOUT audience/issuer verification, to inspect or tamper."""
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"verify_aud": False, "verify_iss": False},
    )


def _resign(claims: dict) -> str:
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# JWT: iss/aud hardening
# ---------------------------------------------------------------------------


def test_create_access_token_carries_iss_and_aud_claims():
    token = create_access_token("user-1", extra={"role": "admin"})
    claims = _raw_claims(token)
    assert claims["iss"] == TOKEN_ISSUER
    assert claims["aud"] == TOKEN_AUDIENCE


def test_decode_token_accepts_self_issued_token():
    token = create_access_token("user-1", extra={"role": "admin"})
    claims = decode_token(token)
    assert claims["sub"] == "user-1"
    assert claims["role"] == "admin"
    assert claims["iss"] == TOKEN_ISSUER
    assert claims["aud"] == TOKEN_AUDIENCE


def test_decode_token_rejects_wrong_audience():
    token = create_access_token("user-1")
    claims = _raw_claims(token)
    claims["aud"] = "some-other-service"
    with pytest.raises(jwt.InvalidAudienceError):
        decode_token(_resign(claims))


def test_decode_token_rejects_tampered_issuer():
    token = create_access_token("user-1")
    claims = _raw_claims(token)
    claims["iss"] = "evil-platform"
    with pytest.raises(jwt.InvalidIssuerError):
        decode_token(_resign(claims))


def test_decode_token_rejects_token_without_sub():
    import time

    now = int(time.time())
    token = _resign({
        "iss": TOKEN_ISSUER,
        "aud": TOKEN_AUDIENCE,
        "iat": now,
        "exp": now + 3600,
        "jti": "no-sub",
    })
    with pytest.raises(jwt.PyJWTError):
        decode_token(token)


def test_decode_token_rejects_malformed_token():
    with pytest.raises(jwt.PyJWTError):
        decode_token("garbage.token.value")


# ---------------------------------------------------------------------------
# Password complexity (H4)
# ---------------------------------------------------------------------------


def test_complexity_too_short():
    violations = validate_password_complexity("short1A")  # 7 chars
    assert violations == [f"must be at least {settings.PASSWORD_MIN_LENGTH} characters"]


def test_complexity_missing_character_classes():
    violations = validate_password_complexity("alllowercase1")  # lower + digit only
    expected = "must include at least 3 of: lowercase, uppercase, digit, symbol"
    assert expected in violations


def test_complexity_accepts_valid_passwords():
    for pw in ("Passw0rd!", "P@ssw0rd", "short1A!"):  # 8+ chars, >=3 classes
        assert validate_password_complexity(pw) == []


def test_complexity_rejects_single_class_password():
    violations = validate_password_complexity("password")
    assert any("at least 3 of" in v for v in violations)


# ---------------------------------------------------------------------------
# Login rate limiting (C1): in-process fallback must NOT fail open
# ---------------------------------------------------------------------------


class _FailingRedis:
    async def rate_limit(self, key: str, limit: int, window_seconds: int):
        raise ConnectionError("redis down")


@pytest.mark.asyncio
async def test_login_rate_limit_blocks_via_fallback_when_redis_down():
    from fmp.api.v1.auth import _fallback_attempts, login_rate_limited

    _fallback_attempts.clear()
    fake = _FailingRedis()
    try:
        for _ in range(5):
            allowed, remaining = await login_rate_limited(fake, "alice", "10.0.0.1")
            assert allowed is True
            assert remaining >= 0
        allowed, remaining = await login_rate_limited(fake, "alice", "10.0.0.1")
        assert allowed is False
        assert remaining == 0
        # a different user/IP is NOT affected by alice's block
        allowed, _ = await login_rate_limited(fake, "bob", "10.0.0.2")
        assert allowed is True
    finally:
        _fallback_attempts.clear()