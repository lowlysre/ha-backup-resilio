"""Binary sensors for Resilio Backup."""

from __future__ import annotations

from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ResilioDataUpdateCoordinator
from .entity import ResilioEntity

# Coordinator centralizes data updates; this is a read-only platform.
PARALLEL_UPDATES = 0


class ResilioConnectivityBinarySensor(ResilioEntity, BinarySensorEntity):
    """Represent overall folder connectivity."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "connectivity"

    def __init__(
        self,
        coordinator: ResilioDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_connectivity"

    @property
    @override
    def is_on(self) -> bool:
        """Return True if the integration can reach the folder and it is healthy."""
        return self.coordinator.last_update_success and self.coordinator.data.state != "error"


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator: ResilioDataUpdateCoordinator = entry.runtime_data.coordinator
    async_add_entities([ResilioConnectivityBinarySensor(coordinator, entry)])
