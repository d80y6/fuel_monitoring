"""Secure single-use code generation for dispensing authorizations.

Design
------
* Codes are numeric (configurable 6-8 digits), generated from a CSPRNG with
  rejection sampling (no modulo bias).
* Only a salted PBKDF2-SHA256 hash is persisted as the at-rest secret; the
  plaintext code exists only transiently here and in the dispatched message.
* A deterministic HMAC fingerprint is returned alongside the hash so callers
  can store the ``code_fp`` index column and check Redis membership in O(1).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from fmp.core.config import get_settings
from fmp.core.redis import RedisClient
from fmp.core.security import code_fingerprint, generate_secure_code, hash_code

settings = get_settings()

MAX_COLLISION_ATTEMPTS = 5


class CodeGenerationError(RuntimeError):
    pass


HashCheck = Callable[[str], Awaitable[bool]]


async def generate_unique_code(
    redis: RedisClient,
    length: int | None = None,
    existing_hashes_check: HashCheck | None = None,
    existing_fingerprints_check: HashCheck | None = None,
) -> tuple[str, str, str]:
    """Generate a unique code.

    Returns ``(plaintext_code, salted_hash, fingerprint)``.

    Uniqueness is enforced against:
      1. the Redis "used fingerprint" set (hot path),
      2. optional DB checks for existing hashes / fingerprints.
    """
    length = length or secrets.choice(
        range(settings.CODE_LENGTH_MIN, settings.CODE_LENGTH_MAX + 1)
    )

    for _ in range(MAX_COLLISION_ATTEMPTS):
        code = generate_secure_code(length)
        fp = code_fingerprint(code)
        code_hash = hash_code(code)

        if await _fp_known(redis, fp):
            continue
        if existing_fingerprints_check is not None and await existing_fingerprints_check(fp):
            continue
        if existing_hashes_check is not None and await existing_hashes_check(code_hash):
            continue

        # NOTE: nothing is reserved here. Ground truth is the DB unique
        # indexes on (code_fp) and (code_hash); callers persist the tuple in
        # a transaction and retry generation on IntegrityError.
        return code, code_hash, fp

    raise CodeGenerationError(
        "Could not generate a unique code after retries; collision storm detected."
    )


async def _fp_known(redis: RedisClient, fp: str) -> bool:
    """Fast negative: skip codes already consumed (present in used set)."""
    return bool(await redis.client.sismember("dispense:used_fingerprints", fp))


def code_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.CODE_TTL_DAYS)