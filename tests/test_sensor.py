"""Tests for Resilio sensors."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from custom_components.resilio_backup.coordinator import ResilioFolderStatus
from custom_components.resilio_backup.sensor import (
    ResilioFileCountSensor,
    ResilioFolderSizeSensor,
    ResilioLastUpdatedSensor,
    ResilioPeerCountConnectedSensor,
    ResilioPeerCountTotalSensor,
    ResilioSyncStateSensor,
)
from tests.common import build_mock_entry

LAST_SUCCESS = datetime(2026, 8, 30, 23, 0, 0, tzinfo=timezone.utc)


def build_coordinator(state: str = "in_sync") -> SimpleNamespace:
    """Create a coordinator stub."""
    return SimpleNamespace(
        data=ResilioFolderStatus(
            folder_id="folder123",
            name="Home Assistant Backups",
            path="C:\\Resilio\\Backups",
            size=2048,
            files=16,
            peers=3,
            peers_total=5,
            state=state,
            last_success=LAST_SUCCESS,
        ),
        last_update_success=True,
    )


def test_sync_state_sensor_normalizes_state(hass) -> None:
    """The enum sensor exposes normalized states."""
    entry = build_mock_entry(hass)
    sensor = ResilioSyncStateSensor(build_coordinator("SYNCING"), entry)
    assert sensor.native_value == "syncing"
    assert sensor.translation_key == "sync_state"


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
    file_count_sensor = ResilioFileCountSensor(coordinator, entry)
    assert file_count_sensor.native_value == 16
    assert file_count_sensor.translation_key == "file_count"
    peer_count_sensor = ResilioPeerCountConnectedSensor(coordinator, entry)
    assert peer_count_sensor.native_value == 3
    assert peer_count_sensor.translation_key == "peer_count_connected"
    peer_count_total_sensor = ResilioPeerCountTotalSensor(coordinator, entry)
    assert peer_count_total_sensor.native_value == 5
    assert peer_count_total_sensor.translation_key == "peer_count_total"


def test_last_updated_sensor(hass) -> None:
    """The last-updated sensor exposes the coordinator's last success timestamp."""
    entry = build_mock_entry(hass)
    sensor = ResilioLastUpdatedSensor(build_coordinator(), entry)
    assert sensor.native_value == LAST_SUCCESS
    assert sensor.translation_key == "last_updated"
