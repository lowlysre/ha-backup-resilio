"""Data coordinator for Resilio Backup."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    ResilioApiClient,
    ResilioAuthError,
    ResilioConnectionError,
    ResilioFolderNotFoundError,
)
from .const import (
    CONF_FOLDER_ID,
    EVENT_FILE_COUNT_CHANGED,
    EVENT_PEER_COUNT_CHANGED,
    SCAN_INTERVAL,
)
from .folder_state import derive_sync_state, safe_int

LOGGER = logging.getLogger(__name__)

# Kept as a module-level alias: tests and any external callers already import
# `_safe_int` from here, and the real implementation now lives in
# `folder_state.py` so it can be imported without Home Assistant installed.
_safe_int = safe_int


@dataclass(frozen=True, kw_only=True)
class ResilioFolderStatus:
    """Normalized folder status from the Resilio API."""

    folder_id: str
    name: str
    path: str
    size: int
    files: int
    peers: int
    state: str


class ResilioDataUpdateCoordinator(DataUpdateCoordinator[ResilioFolderStatus]):
    """Fetch and normalize folder status."""

    def __init__(
        self,
        hass,
        entry: ConfigEntry,
        client: ResilioApiClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name="Resilio Backup",
            update_interval=SCAN_INTERVAL,
            always_update=False,
        )
        self._entry = entry
        self._client = client

    async def _async_update_data(self) -> ResilioFolderStatus:
        """Fetch the latest folder status."""
        try:
            folder = await self._client.async_get_folder(self._entry.data[CONF_FOLDER_ID])
        except (
            ResilioConnectionError,
            ResilioAuthError,
            ResilioFolderNotFoundError,
        ) as err:
            raise UpdateFailed(str(err)) from err

        status = ResilioFolderStatus(
            folder_id=str(folder.get("id", self._entry.data[CONF_FOLDER_ID])),
            name=str(
                folder.get("name")
                or folder.get("path")
                or self._entry.data[CONF_FOLDER_ID]
            ),
            path=str(folder.get("path", "")),
            size=_safe_int(folder.get("size")),
            files=_safe_int(folder.get("files")),
            peers=_safe_int(folder.get("peers")),
            state=derive_sync_state(folder),
        )
        self._fire_change_events(status)
        return status

    def _fire_change_events(self, status: ResilioFolderStatus) -> None:
        """Fire logbook-visible events when peer or file counts change."""
        previous = self.data
        if previous is None:
            return

        if status.peers != previous.peers:
            self.hass.bus.async_fire(
                EVENT_PEER_COUNT_CHANGED,
                {
                    "entry_id": self._entry.entry_id,
                    "previous": previous.peers,
                    "current": status.peers,
                },
            )

        if status.files != previous.files:
            self.hass.bus.async_fire(
                EVENT_FILE_COUNT_CHANGED,
                {
                    "entry_id": self._entry.entry_id,
                    "previous": previous.files,
                    "current": status.files,
                },
            )
