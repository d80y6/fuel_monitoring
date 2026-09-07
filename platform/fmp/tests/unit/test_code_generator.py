"""Unit tests for secure code generation (no external infrastructure)."""
from __future__ import annotations

import pytest

from fmp.core.security import code_fingerprint, generate_secure_code, hash_code, verify_code
from fmp.services.dispensing.code_generator import (
    MAX_COLLISION_ATTEMPTS,
    CodeGenerationError,
    generate_unique_code,
)
from fmp.tests.conftest import FakeRedis


def test_generate_secure_code_shape_and_randomness():
    codes = {generate_secure_code(8) for _ in range(50)}
    assert all(len(c) == 8 and c.isdigit() for c in codes)
    assert len(codes) > 40  # random enough


def test_generate_secure_code_min_length():
    with pytest.raises(ValueError):
        generate_secure_code(3)


def test_hash_verify_roundtrip_and_salting():
    h1, h2 = hash_code("123456"), hash_code("123456")
    assert verify_code("123456", h1)
    assert not verify_code("654321", h1)
    assert h1 != h2  # random salt


def test_fingerprint_deterministic_and_non_reversible():
    fp1, fp2 = code_fingerprint("777222"), code_fingerprint("777222")
    assert fp1 == fp2 and len(fp1) == 64
    # fingerprint != salted hash
    assert fp1 != hash_code("777222").split("$")[1]


@pytest.mark.asyncio
async def test_generate_unique_code_avoids_used_fingerprints():
    redis = FakeRedis()
    existing_fps = {"x" * 64}
    existing_hashes = {"y" * 64}

    async def fp_check(fp: str) -> bool:
        return fp in existing_fps

    async def hash_check(h: str) -> bool:
        return h in existing_hashes

    code, code_hash, fp = await generate_unique_code(redis, length=8, existing_hashes_check=hash_check, existing_fingerprints_check=fp_check)
    assert fp not in existing_fps
    assert verify_code(code, code_hash)
    assert len(code) == 8


@pytest.mark.asyncio
async def test_generate_unique_code_ok_without_infra():
    redis = FakeRedis()
    code, code_hash, fp = await generate_unique_code(redis, length=6)
    assert len(code) == 6 and code.isdigit()
    assert len(fp) == 64
    assert verify_code(code, code_hash)


@pytest.mark.asyncio
async def test_collision_storm_raises():
    redis = FakeRedis()

    async def always_true(h: str) -> bool:
        return True

    with pytest.raises(CodeGenerationError):
        await generate_unique_code(
            redis, length=6, existing_fingerprints_check=always_true
        )