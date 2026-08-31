"""Sensor platform for Resilio Backup."""

from __future__ import annotations

from datetime import datetime
from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfInformation
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.core import HomeAssistant

from .coordinator import ResilioDataUpdateCoordinator
from .entity import ResilioEntity


class ResilioSyncStateSensor(ResilioEntity, SensorEntity):
    """Expose the current folder sync state."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["in_sync", "syncing", "paused", "error", "unknown"]
    _attr_translation_key = "sync_state"
    _attr_icon = "mdi:folder-sync"

    def __init__(
        self,
        coordinator: ResilioDataUpdateCoordinator,
        entry: ConfigEntry,
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
        entry: ConfigEntry,
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
    _attr_icon = "mdi:file-document-multiple"

    def __init__(
        self,
        coordinator: ResilioDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_file_count"

    @property
    @override
    def native_value(self) -> int:
        """Return the file count."""
        return self.coordinator.data.files


class ResilioPeerCountSensor(ResilioEntity, SensorEntity):
    """Expose the connected peer count."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "peer_count"
    _attr_icon = "mdi:account-switch"

    def __init__(
        self,
        coordinator: ResilioDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_peer_count"

    @property
    @override
    def native_value(self) -> int:
        """Return the peer count."""
        return self.coordinator.data.peers


class ResilioLastUpdatedSensor(ResilioEntity, SensorEntity):
    """Expose the timestamp of the last successful poll."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "last_updated"
    _attr_icon = "mdi:clock-check-outline"

    def __init__(
        self,
        coordinator: ResilioDataUpdateCoordinator,
        entry: ConfigEntry,
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
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Resilio Backup sensors."""
    coordinator: ResilioDataUpdateCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            ResilioSyncStateSensor(coordinator, entry),
            ResilioFolderSizeSensor(coordinator, entry),
            ResilioFileCountSensor(coordinator, entry),
            ResilioPeerCountSensor(coordinator, entry),
            ResilioLastUpdatedSensor(coordinator, entry),
        ]
    )
