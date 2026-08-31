"""Describe Resilio Backup logbook events."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.logbook import LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN, EVENT_BACKUPS_PRUNED, EVENT_FILE_COUNT_CHANGED, EVENT_PEER_COUNT_CHANGED


def _entry_title(hass: HomeAssistant, entry_id: str) -> str:
    """Return the config entry title, or a fallback if it's gone."""
    entry = hass.config_entries.async_get_entry(entry_id)
    return entry.title if entry is not None else "Resilio Backup"


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, str]]], None],
) -> None:
    """Describe Resilio Backup logbook events."""

    @callback
    def async_describe_peer_count_changed(event: Event) -> dict[str, str]:
        """Describe a peer count change."""
        data = event.data
        previous, current = data["previous"], data["current"]
        direction = "connected" if current > previous else "disconnected"
        return {
            LOGBOOK_ENTRY_NAME: _entry_title(hass, data["entry_id"]),
            LOGBOOK_ENTRY_MESSAGE: f"a peer {direction} ({previous} \u2192 {current} peers)",
        }

    @callback
    def async_describe_file_count_changed(event: Event) -> dict[str, str]:
        """Describe a file count change."""
        data = event.data
        return {
            LOGBOOK_ENTRY_NAME: _entry_title(hass, data["entry_id"]),
            LOGBOOK_ENTRY_MESSAGE: (
                f"file count changed from {data['previous']} to {data['current']}"
            ),
        }

    @callback
    def async_describe_backups_pruned(event: Event) -> dict[str, str]:
        """Describe a prune run."""
        data = event.data
        deleted = data["deleted"]
        suffix = "" if deleted == 1 else "s"
        return {
            LOGBOOK_ENTRY_NAME: _entry_title(hass, data["entry_id"]),
            LOGBOOK_ENTRY_MESSAGE: f"pruned {deleted} old backup{suffix}",
        }

    async_describe_event(DOMAIN, EVENT_PEER_COUNT_CHANGED, async_describe_peer_count_changed)
    async_describe_event(DOMAIN, EVENT_FILE_COUNT_CHANGED, async_describe_file_count_changed)
    async_describe_event(DOMAIN, EVENT_BACKUPS_PRUNED, async_describe_backups_pruned)
