"""Sensor platform for Resilio Backup."""

from __future__ import annotations

from datetime import datetime
from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfInformation
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.core import HomeAssistant

from .coordinator import ResilioConfigEntry, ResilioDataUpdateCoordinator
from .entity import ResilioEntity

# Coordinator centralizes data updates; this is a read-only platform.
PARALLEL_UPDATES = 0


class ResilioSyncStateSensor(ResilioEntity, SensorEntity):
    """Expose the current folder sync state."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["in_sync", "syncing", "paused", "error", "unknown"]
    _attr_translation_key = "sync_state"

    def __init__(
        self,
        coordinator: ResilioDataUpdateCoordinator,
        entry: ResilioConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_sync_state"

    @property
    @override
    def native_value(self) -> str:
        """Return the current sync state."""
        state = self.coordinator.data.state.lower().replace(" ", "_")
        return state if state in self._attr_options else "unknown"


class ResilioFolderSizeSensor(ResilioEntity, SensorEntity):
    """Expose the folder size."""

    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.BYTES
    _attr_suggested_display_precision = 2
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "folder_size"

    def __init__(
        self,
        coordinator: ResilioDataUpdateCoordinator,
        entry: ResilioConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_folder_size"

    @property
    @override
    def native_value(self) -> int:
        """Return the folder size."""
        return self.coordinator.data.size


class ResilioFileCountSensor(ResilioEntity, SensorEntity):
    """Expose the file count."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "file_count"

    def __init__(
        self,
        coordinator: ResilioDataUpdateCoordinator,
        entry: ResilioConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_file_count"

    @property
    @override
    def native_value(self) -> int:
        """Return the file count."""
        return self.coordinator.data.files


class ResilioPeerCountConnectedSensor(ResilioEntity, SensorEntity):
    """Expose the connected peer count."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "peer_count_connected"

    def __init__(
        self,
        coordinator: ResilioDataUpdateCoordinator,
        entry: ResilioConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_peer_count_connected"

    @property
    @override
    def native_value(self) -> int:
        """Return the connected peer count."""
        return self.coordinator.data.peers


class ResilioPeerCountTotalSensor(ResilioEntity, SensorEntity):
    """Expose the total number of peers configured for the folder."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "peer_count_total"

    def __init__(
        self,
        coordinator: ResilioDataUpdateCoordinator,
        entry: ResilioConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_peer_count_total"

    @property
    @override
    def native_value(self) -> int:
        """Return the configured peer count, connected or not."""
        return self.coordinator.data.peers_total


class ResilioLastUpdatedSensor(ResilioEntity, SensorEntity):
    """Expose the timestamp of the last successful poll."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "last_updated"

    def __init__(
        self,
        coordinator: ResilioDataUpdateCoordinator,
        entry: ResilioConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_last_updated"

    @property
    @override
    def native_value(self) -> datetime:
        """Return the timestamp of the last successful update."""
        return self.coordinator.data.last_success


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ResilioConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Resilio Backup sensors."""
    coordinator: ResilioDataUpdateCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            ResilioSyncStateSensor(coordinator, entry),
            ResilioFolderSizeSensor(coordinator, entry),
            ResilioFileCountSensor(coordinator, entry),
            ResilioPeerCountConnectedSensor(coordinator, entry),
            ResilioPeerCountTotalSensor(coordinator, entry),
            ResilioLastUpdatedSensor(coordinator, entry),
        ]
    )
