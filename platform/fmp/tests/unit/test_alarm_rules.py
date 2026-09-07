"""Unit tests for alarm rule evaluation (threshold crossings)."""
from __future__ import annotations

import uuid

import pytest

from fmp.ingestion.pipeline import AlarmCandidate, evaluate_alarm_rules


def _tank(**overrides):
    from fmp.models import Tank

    defaults = dict(
        id=uuid.uuid4(),
        name="T1",
        low_level_threshold=0.4,
        critical_level_threshold=0.2,
        high_level_threshold=4.8,
        low_volume_threshold=800.0,
        high_volume_threshold=None,
    )
    defaults.update(overrides)
    return Tank(**defaults)


def test_no_thresholds_no_crossing_no_alarm():
    tank = _tank(
        low_level_threshold=None, critical_level_threshold=None,
        high_level_threshold=None, low_volume_threshold=None,
    )
    assert evaluate_alarm_rules(tank, level=2.0, volume=1000.0, fill_percent=50.0) == []


def test_high_level_crossing():
    candidates = evaluate_alarm_rules(_tank(), level=4.9, volume=1000.0, fill_percent=50.0)
    assert any(c.type == "high_level" and c.level == "WARNING" for c in candidates)


def test_critical_level_crossing():
    candidates = evaluate_alarm_rules(_tank(), level=0.15, volume=1000.0, fill_percent=50.0)
    assert any(c.type == "critical_level" and c.level == "CRITICAL" for c in candidates)


def test_low_level_warning():
    candidates = evaluate_alarm_rules(_tank(), level=0.35, volume=1000.0, fill_percent=50.0)
    assert any(c.type == "low_level" and c.level == "WARNING" for c in candidates)


def test_low_volume_warning():
    candidates = evaluate_alarm_rules(_tank(), level=1.0, volume=700.0, fill_percent=50.0)
    assert any(c.type == "low_volume" and c.level == "WARNING" for c in candidates)


def test_steady_state_produces_no_alarm():
    tank = _tank()
    assert evaluate_alarm_rules(tank, level=2.0, volume=1500.0, fill_percent=50.0) == []


def test_candidates_carried_value_is_measurement_value():
    candidates = evaluate_alarm_rules(_tank(), level=0.15, volume=1000.0, fill_percent=99.0)
    cand = next(c for c in candidates if c.type == "critical_level")
    assert cand.value == 0.15
    assert cand.message