"""Unit tests: IoT gateway + command schema payload validation."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from fmp.schemas.iot import IoTCommandCreate


def test_reboot_requires_empty_payload():
    cmd = IoTCommandCreate(command_type="reboot", payload={})
    assert cmd.payload == {}


def test_set_interval_requires_positive_seconds():
    with pytest.raises(ValidationError):
        IoTCommandCreate(command_type="set_interval", payload={})
    with pytest.raises(ValidationError):
        IoTCommandCreate(command_type="set_interval", payload={"interval_s": 0})
    cmd = IoTCommandCreate(command_type="set_interval", payload={"interval_s": 5})
    assert cmd.payload["interval_s"] == 5


def test_recalibrate_requires_sensor_and_reference():
    with pytest.raises(ValidationError):
        IoTCommandCreate(command_type="recalibrate", payload={"sensor": "P1"})
    cmd = IoTCommandCreate(
        command_type="recalibrate",
        payload={"sensor": "P1", "reference_pressure_bar": 0.133},
    )
    assert cmd.payload["reference_pressure_bar"] == 0.133


def test_zero_tank_requires_serial():
    with pytest.raises(ValidationError):
        IoTCommandCreate(command_type="zero_tank", payload={})
    cmd = IoTCommandCreate(command_type="zero_tank", payload={"tank_serial": "SN-1", "level_m": 0.0})
    assert cmd.payload["tank_serial"] == "SN-1"


def test_push_config_requires_nonempty_object():
    with pytest.raises(ValidationError):
        IoTCommandCreate(command_type="push_config", payload={})
    cmd = IoTCommandCreate(command_type="push_config", payload={"interval_s": 5})
    assert cmd.payload["interval_s"] == 5


def test_unknown_command_type_rejected():
    with pytest.raises(ValidationError):
        IoTCommandCreate(command_type="explode", payload={})