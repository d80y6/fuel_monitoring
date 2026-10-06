"""Unit tests for notification-channel secret masking (G-005)."""
from __future__ import annotations

from fmp.services.notifications.secrets import (
    MASK,
    is_secret_key,
    mask_config,
    merge_config,
)


class TestIsSecretKey:
    def test_generic_markers(self):
        assert is_secret_key("password")
        assert is_secret_key("access_token")
        assert is_secret_key("api_key")
        assert is_secret_key("client_secret")
        assert is_secret_key("Authorization")

    def test_non_secret_keys(self):
        assert not is_secret_key("host")
        assert not is_secret_key("port")
        assert not is_secret_key("url")
        assert not is_secret_key("sender")

    def test_channel_specific_identifier_counts_as_secret(self):
        # SMPP system_id is an account identifier, not a public value.
        assert is_secret_key("system_id", "smpp")
        assert is_secret_key("phone_number_id", "whatsapp")


class TestMaskConfig:
    def test_masks_values_and_keeps_keys(self):
        cfg = {"host": "smsc.example.com", "port": 2775, "password": "hunter2"}
        masked = mask_config(cfg, "smpp")
        assert masked["host"] == "smsc.example.com"
        assert masked["port"] == 2775
        assert masked["password"] == MASK
        assert "password" in masked  # key presence preserved for the UI

    def test_empty_config(self):
        assert mask_config(None) == {}
        assert mask_config({}) == {}

    def test_does_not_mutate_input(self):
        cfg = {"password": "hunter2"}
        mask_config(cfg, "smpp")
        assert cfg["password"] == "hunter2"


class TestMergeConfig:
    def test_mask_echo_preserves_stored_secret(self):
        merged = merge_config(
            {"host": "h", "password": "real-secret"}, {"password": MASK}, "smpp"
        )
        assert merged["password"] == "real-secret"

    def test_omitted_secret_is_preserved(self):
        merged = merge_config(
            {"host": "h", "password": "real-secret"}, {"host": "new"}, "smpp"
        )
        assert merged["password"] == "real-secret"
        assert merged["host"] == "new"

    def test_new_secret_replaces_stored(self):
        merged = merge_config(
            {"host": "h", "password": "old"}, {"password": "new-secret"}, "smpp"
        )
        assert merged["password"] == "new-secret"

    def test_non_secret_omission_removes_key(self):
        merged = merge_config({"host": "h", "port": 2775}, {"host": "h2"}, "smpp")
        assert "port" not in merged
        assert merged["host"] == "h2"

    def test_none_incoming_is_a_no_op(self):
        stored = {"host": "h", "password": "s"}
        assert merge_config(stored, None, "smpp") == stored

    def test_secret_on_unconfigured_channel_gets_masked(self):
        # Operator posts a brand-new channel with a password; the stored value
        # is real, but a read must still mask it.
        merged = merge_config({}, {"password": "fresh"}, "smpp")
        assert merged["password"] == "fresh"
        assert mask_config(merged, "smpp")["password"] == MASK
