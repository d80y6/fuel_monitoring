"""Device key minting and verification (G-113).

Covers the crypto primitive behind station API keys: a station key must be
unguessable, stored only as a salted hash, verifiable in constant time, and
must never be confused with a user password.
"""
from __future__ import annotations

import pytest

from fmp.core.device_auth import (
    DEVICE_KEY_ITERATIONS,
    _hash_device_key,
    _verify_device_key,
    generate_station_key,
)


class TestGenerateStationKey:
    def test_returns_prefixed_plaintext_hash_and_prefix(self):
        plain, hashed, prefix = generate_station_key()
        assert plain.startswith("fmk_")
        assert prefix == plain[:12]
        assert hashed.startswith("pbkdf2_sha256$")
        assert plain not in hashed

    def test_hashed_format_carries_iterations_salt_and_digest(self):
        _plain, hashed, _prefix = generate_station_key()
        prefix_tag, iterations, salt, digest = hashed.split("$")
        assert prefix_tag == "pbkdf2_sha256"
        assert int(iterations) == DEVICE_KEY_ITERATIONS
        assert salt and digest

    def test_keys_are_unique_per_call(self):
        keys = {generate_station_key()[0] for _ in range(8)}
        assert len(keys) == 8


class TestVerifyDeviceKey:
    def test_accepts_the_issued_key(self):
        plain, hashed, _prefix = generate_station_key()
        assert _verify_device_key(plain, hashed) is True

    def test_rejects_a_different_key(self):
        _plain, hashed, _prefix = generate_station_key()
        assert _verify_device_key("fmk_totally-different", hashed) is False

    def test_rejects_empty_key(self):
        _plain, hashed, _prefix = generate_station_key()
        assert _verify_device_key("", hashed) is False

    @pytest.mark.parametrize(
        "stored",
        [
            "not-a-hash",
            "pbkdf2_sha256$notanumber$abc$def",
            "pbkdf2_sha256$120000",
            "md5$1$2$3",
            "",
        ],
    )
    def test_malformed_stored_hash_never_verifies(self, stored):
        """A corrupted hash must fail closed, never raise or pass."""
        assert _verify_device_key("fmk_anything", stored) is False

    def test_salted_so_identical_keys_hash_differently(self):
        """Two stations with the same secret must not share a stored hash."""
        assert _hash_device_key("fmk_same") != _hash_device_key("fmk_same")