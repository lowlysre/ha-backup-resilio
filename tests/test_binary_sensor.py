"""Tests for the Resilio binary sensor."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.resilio_backup.coordinator import ResilioFolderStatus
from custom_components.resilio_backup.binary_sensor import ResilioConnectivityBinarySensor
from tests.common import build_mock_entry


def build_coordinator(state: str = "in_sync", success: bool = True) -> SimpleNamespace:
    """Create a coordinator stub."""
    return SimpleNamespace(
        data=ResilioFolderStatus(
            folder_id="folder123",
            name="Home Assistant Backups",
            path="C:\\Resilio\\Backups",
            size=2048,
            files=16,
            peers=3,
            peers_total=3,
            state=state,
        ),
        last_update_success=success,
    )


def test_connectivity_binary_sensor_healthy(hass) -> None:
    """Healthy state reports on."""
    entry = build_mock_entry(hass)
    entity = ResilioConnectivityBinarySensor(build_coordinator(), entry)
    assert entity.is_on is True


def test_connectivity_binary_sensor_error_state(hass) -> None:
    """Folder error state reports off."""
    entry = build_mock_entry(hass)
    entity = ResilioConnectivityBinarySensor(build_coordinator("error"), entry)
    assert entity.is_on is False


def test_connectivity_binary_sensor_unavailable(hass) -> None:
    """Coordinator failure reports off."""
    entry = build_mock_entry(hass)
    entity = ResilioConnectivityBinarySensor(build_coordinator(success=False), entry)
    assert entity.is_on is False
