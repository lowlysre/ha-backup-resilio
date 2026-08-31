"""Tests for the Resilio binary sensor."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.resilio_backup.coordinator import ResilioFolderStatus
from custom_components.resilio_backup.binary_sensor import (
    ResilioConnectivityBinarySensor,
    ResilioPerformanceWarningBinarySensor,
)
from tests.common import build_mock_entry


def build_coordinator(
    state: str = "in_sync",
    success: bool = True,
    performance_warnings: tuple[str, ...] = (),
) -> SimpleNamespace:
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
            performance_warnings=performance_warnings,
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


def test_performance_warning_binary_sensor_no_warnings(hass) -> None:
    """No reported warnings means off, with an empty attribute list."""
    entry = build_mock_entry(hass)
    entity = ResilioPerformanceWarningBinarySensor(build_coordinator(), entry)
    assert entity.is_on is False
    assert entity.extra_state_attributes == {"warnings": []}


def test_performance_warning_binary_sensor_has_warnings(hass) -> None:
    """A non-empty warning list reports on and surfaces the raw messages."""
    entry = build_mock_entry(hass)
    entity = ResilioPerformanceWarningBinarySensor(
        build_coordinator(performance_warnings=("Low disk space",)), entry
    )
    assert entity.is_on is True
    assert entity.extra_state_attributes == {"warnings": ["Low disk space"]}
