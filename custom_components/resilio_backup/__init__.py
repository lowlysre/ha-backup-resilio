"""The Resilio Backup integration."""

from __future__ import annotations

from functools import partial

from homeassistant.components import persistent_notification
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STARTED,
    Platform,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .api import ResilioApiClient
from .backup import async_notify_backup_listeners
from .const import (
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DATA_PENDING_LOCATIONS_CHECK,
    DOMAIN,
)
from .coordinator import ResilioBackupData, ResilioConfigEntry, ResilioDataUpdateCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def _async_handle_pending_locations_check(hass: HomeAssistant, _event: Event) -> None:
    """Remind about backup Locations after a restart following a real reconfigure.

    Only fires on a genuine full Home Assistant restart (this listens for
    ``EVENT_HOMEASSISTANT_STARTED``, which a live config entry reload never
    triggers), matching when HA's backup manager would have had a chance to
    lose track of this integration's agent across the reconfigure-triggered
    reload (lowlysre/ha-backup-resilio#30).
    """
    for entry in hass.config_entries.async_entries(DOMAIN):
        if not entry.data.get(DATA_PENDING_LOCATIONS_CHECK):
            continue
        persistent_notification.async_create(
            hass,
            (
                "Resilio Backup's connection settings changed last session. "
                "If it isn't already selected under Settings > Backups > "
                "Locations, re-select it now."
            ),
            title="Resilio Backup: check backup locations",
            notification_id=f"{DOMAIN}_locations_check_{entry.entry_id}",
        )
        hass.config_entries.async_update_entry(
            entry,
            data={
                key: value
                for key, value in entry.data.items()
                if key != DATA_PENDING_LOCATIONS_CHECK
            },
        )


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up the integration."""
    hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STARTED, partial(_async_handle_pending_locations_check, hass)
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
