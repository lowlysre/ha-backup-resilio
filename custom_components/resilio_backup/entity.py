"""Shared entity classes for Resilio Backup."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import ResilioConfigEntry, ResilioDataUpdateCoordinator


class ResilioEntity(CoordinatorEntity[ResilioDataUpdateCoordinator]):
    """Base entity for Resilio Backup."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ResilioDataUpdateCoordinator,
        entry: ResilioConfigEntry,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model="Sync Folder",
            configuration_url=f"http://{entry.data[CONF_HOST]}:{entry.data[CONF_PORT]}",
        )
