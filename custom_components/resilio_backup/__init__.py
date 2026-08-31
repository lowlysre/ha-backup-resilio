"""The Resilio Backup integration."""

from __future__ import annotations

from functools import partial

from homeassistant.config_entries import ConfigEntryState
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
from .coordinator import ResilioBackupData, ResilioConfigEntry, ResilioDataUpdateCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def _async_handle_prune_service(hass: HomeAssistant, _call: ServiceCall) -> None:
    """Handle pruning old backups for all loaded entries."""
    loaded_entry: ResilioConfigEntry
    for loaded_entry in hass.config_entries.async_entries(DOMAIN):
        if loaded_entry.state is ConfigEntryState.LOADED:
            await async_prune_backups(hass, loaded_entry)


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up the integration."""
    hass.services.async_register(
        DOMAIN, SERVICE_PRUNE_BACKUPS, partial(_async_handle_prune_service, hass)
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ResilioConfigEntry) -> bool:
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

    async_notify_backup_listeners(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ResilioConfigEntry) -> bool:
    """Unload a Resilio Backup entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    async_notify_backup_listeners(hass)
    return True
