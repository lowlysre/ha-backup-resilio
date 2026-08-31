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
from .const import CONF_FOLDER_ID, SCAN_INTERVAL

LOGGER = logging.getLogger(__name__)


def _safe_int(value: object, default: int = 0) -> int:
    """Coerce a Resilio field to an int, tolerating shapes the WebUI API doesn't document.

    The `/gui/` action API isn't documented, so a field observed as a scalar in one
    Resilio version can turn out to be a list (e.g. `peers` listing peer objects
    instead of a count) in another. Falling back to `len()` for list/tuple values,
    and to `default` for anything else that doesn't cleanly convert, keeps a single
    unexpected shape from crashing the whole coordinator refresh.
    """
    if isinstance(value, (list, tuple)):
        return len(value)
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


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

        return ResilioFolderStatus(
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
            state=str(folder.get("state", "unknown")).lower(),
        )
