"""Unit tests: fuel/{mac}/topic routing + payload frame handling."""
from __future__ import annotations

from fmp.ingestion.main import parse_fuel_topic


def test_parse_fuel_readings_topic():
    assert parse_fuel_topic("fuel/AA:BB:CC:DD:EE:01/readings") == ("AA:BB:CC:DD:EE:01", "readings", None)


def test_parse_fuel_status_topic():
    assert parse_fuel_topic("fuel/AA:BB:CC:DD:EE:01/status") == ("AA:BB:CC:DD:EE:01", "status", None)


def test_parse_non_fuel_topic_returns_none():
    assert parse_fuel_topic("ingestion/readings") is None
    assert parse_fuel_topic("fuel/readings") is None
