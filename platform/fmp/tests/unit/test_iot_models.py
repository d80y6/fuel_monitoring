"""Unit tests: IoTGateway + GatewayCommand model shape (no DB)."""
from __future__ import annotations

from fmp.models.gateway import COMMAND_TYPES, GatewayCommand, IoTGateway
from fmp.models.tank import Tank


def test_command_types_catalog():
    assert set(COMMAND_TYPES) == {
        "reboot", "status_probe", "pause_reporting", "resume_reporting",
        "set_interval", "recalibrate", "zero_tank", "push_config",
    }


def test_gateway_columns():
    cols = IoTGateway.__table__.columns.keys()
    for name in ("id", "gateway_mac", "name", "firmware_version",
                 "last_seen", "connection_status", "is_active"):
        assert name in cols


def test_command_columns():
    cols = GatewayCommand.__table__.columns.keys()
    for name in ("id", "gateway_id", "command_id", "command_type", "payload_json",
                 "status", "attempts", "max_attempts", "sent_at", "next_retry_at",
                 "ack_status", "ack_detail", "ack_received_at", "error_message"):
        assert name in cols


def test_tank_has_gateway_fk():
    assert "gateway_id" in Tank.__table__.columns.keys()