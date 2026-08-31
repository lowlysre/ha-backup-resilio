"""Tests for Resilio sensors."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.resilio_backup.coordinator import ResilioFolderStatus
from custom_components.resilio_backup.sensor import (
    ResilioFileCountSensor,
    ResilioFolderSizeSensor,
    ResilioPeerCountSensor,
    ResilioSyncStateSensor,
)
from tests.common import build_mock_entry


def build_coordinator(state: str = "in sync") -> SimpleNamespace:
    """Create a coordinator stub."""
    return SimpleNamespace(
        data=ResilioFolderStatus(
            folder_id="folder123",
            name="Home Assistant Backups",
            path="C:\\Resilio\\Backups",
            size=2048,
            files=16,
            peers=3,
            state=state,
        ),
        last_update_success=True,
    )


def test_sync_state_sensor_normalizes_state(hass) -> None:
    """The enum sensor exposes normalized states."""
    entry = build_mock_entry(hass)
    sensor = ResilioSyncStateSensor(build_coordinator("SYNCING"), entry)
    assert sensor.native_value == "syncing"


def test_sync_state_sensor_falls_back_to_unknown(hass) -> None:
    """Unexpected states fall back to unknown."""
    entry = build_mock_entry(hass)
    sensor = ResilioSyncStateSensor(build_coordinator("broken?"), entry)
    assert sensor.native_value == "unknown"


def test_size_file_and_peer_sensors(hass) -> None:
    """Numeric sensors expose coordinator data."""
    entry = build_mock_entry(hass)
    coordinator = build_coordinator()
    assert ResilioFolderSizeSensor(coordinator, entry).native_value == 2048
    assert ResilioFileCountSensor(coordinator, entry).native_value == 16
    assert ResilioPeerCountSensor(coordinator, entry).native_value == 3
