"""Binary sensors for Resilio Backup."""

from __future__ import annotations

from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ResilioConfigEntry, ResilioDataUpdateCoordinator
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
        entry: ResilioConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_connectivity"

    @property
    @override
    def is_on(self) -> bool:
        """Return True if the integration can reach the folder and it is healthy."""
        return self.coordinator.last_update_success and self.coordinator.data.state != "error"


class ResilioPerformanceWarningBinarySensor(ResilioEntity, BinarySensorEntity):
    """Represent whether Resilio itself is reporting a degraded state.

    Backed by the WebUI's ``getperformancewarnings`` action, the closest
    thing Resilio's own API has to a real health check (low disk, stalled
    sync, and similar issues), as opposed to a plain reachability probe.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "performance_warning"

    def __init__(
        self,
        coordinator: ResilioDataUpdateCoordinator,
        entry: ResilioConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_performance_warning"

    @property
    @override
    def is_on(self) -> bool:
        """Return True if Resilio is reporting at least one performance warning."""
        return bool(self.coordinator.data.performance_warnings)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, list[str]]:
        """Return the raw warning messages Resilio reported."""
        return {"warnings": list(self.coordinator.data.performance_warnings)}


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ResilioConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator: ResilioDataUpdateCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            ResilioConnectivityBinarySensor(coordinator, entry),
            ResilioPerformanceWarningBinarySensor(coordinator, entry),
        ]
    )
