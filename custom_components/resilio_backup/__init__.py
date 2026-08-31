"""The Resilio Backup integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType

from .api import ResilioApiClient
from .backup import async_notify_backup_listeners, async_prune_backups
from .const import (
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DOMAIN,
    SERVICE_PRUNE_BACKUPS,
)
from .coordinator import ResilioDataUpdateCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


@dataclass
class ResilioBackupData:
    """Runtime data for a Resilio config entry."""

    client: ResilioApiClient
    coordinator: ResilioDataUpdateCoordinator


async def async_setup(_hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up the integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Resilio Backup from a config entry."""
    client = ResilioApiClient(
        hass,
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_USE_SSL],
        entry.data[CONF_VERIFY_SSL],
    )
    coordinator = ResilioDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = ResilioBackupData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.services.has_service(DOMAIN, SERVICE_PRUNE_BACKUPS):

        async def _async_handle_prune_service(_call: ServiceCall) -> None:
            """Handle pruning old backups for all loaded entries."""
            for loaded_entry in hass.config_entries.async_entries(DOMAIN):
                if loaded_entry.state is ConfigEntryState.LOADED:
                    await async_prune_backups(hass, loaded_entry)

        hass.services.async_register(
            DOMAIN, SERVICE_PRUNE_BACKUPS, _async_handle_prune_service
        )

    async_notify_backup_listeners(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Resilio Backup entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    if len(hass.config_entries.async_entries(DOMAIN)) == 1:
        hass.services.async_remove(DOMAIN, SERVICE_PRUNE_BACKUPS)

    async_notify_backup_listeners(hass)
    return True
