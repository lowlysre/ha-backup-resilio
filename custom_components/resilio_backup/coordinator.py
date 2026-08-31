"""Data coordinator for Resilio Backup."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    ResilioApiClient,
    ResilioApiError,
    ResilioAuthError,
    ResilioConnectionError,
    ResilioFolderNotFoundError,
)
from .const import (
    CONF_FOLDER_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_FILE_COUNT_CHANGED,
    EVENT_PEER_COUNT_CHANGED,
    ISSUE_FOLDER_NOT_FOUND,
)
from .folder_state import derive_sync_state, peer_counts, safe_int

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
    peers_total: int
    state: str
    last_success: datetime = field(default_factory=dt_util.utcnow)
    resilio_version: str | None = None
    performance_warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class ResilioBackupData:
    """Runtime data for a Resilio config entry.

    Defined here, rather than in ``__init__.py``, so this module and the
    ``ResilioConfigEntry`` alias below can be imported by every other module
    that needs the typed config entry, without a circular import back to
    ``__init__.py``.
    """

    client: ResilioApiClient
    coordinator: ResilioDataUpdateCoordinator


type ResilioConfigEntry = ConfigEntry[ResilioBackupData]


class ResilioDataUpdateCoordinator(DataUpdateCoordinator[ResilioFolderStatus]):
    """Fetch and normalize folder status."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ResilioConfigEntry,
        client: ResilioApiClient,
    ) -> None:
        """Initialize the coordinator."""
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name="Resilio Backup",
            update_interval=timedelta(seconds=scan_interval),
            always_update=False,
        )
        self._entry = entry
        self._client = client
        self._folder_not_found_issue_id = f"{ISSUE_FOLDER_NOT_FOUND}_{entry.entry_id}"

    async def _async_update_data(self) -> ResilioFolderStatus:
        """Fetch the latest folder status."""
        try:
            folder = await self._client.async_get_folder(self._entry.data[CONF_FOLDER_ID])
        except ResilioAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ResilioFolderNotFoundError as err:
            # The folder was removed or renamed on the Resilio side; retrying
            # won't fix this, so raise a repair issue pointing the user at
            # reconfigure instead of just leaving entities unavailable.
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._folder_not_found_issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=ISSUE_FOLDER_NOT_FOUND,
                translation_placeholders={
                    "folder_id": self._entry.data[CONF_FOLDER_ID]
                },
            )
            raise UpdateFailed(str(err)) from err
        except ResilioConnectionError as err:
            raise UpdateFailed(str(err)) from err

        ir.async_delete_issue(self.hass, DOMAIN, self._folder_not_found_issue_id)

        previous = self.data
        peers, peers_total = peer_counts(folder)
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
            peers=peers,
            peers_total=peers_total,
            state=derive_sync_state(folder),
            last_success=dt_util.utcnow(),
            resilio_version=await self._async_get_resilio_version(previous),
            performance_warnings=await self._async_get_performance_warnings(previous),
        )
        self._fire_change_events(status)
        return status

    async def _async_get_resilio_version(
        self, previous: ResilioFolderStatus | None
    ) -> str | None:
        """Fetch Resilio Sync's own version, falling back to the last known value.

        Not fatal: an older Resilio agent that rejects this action shouldn't
        take down the whole update, and a stale-but-known version is more
        useful than blanking a diagnostic sensor on a single failed probe.
        """
        try:
            payload = await self._client.async_get_version()
        except ResilioApiError:
            return previous.resilio_version if previous else None
        value = payload.get("value")
        return str(value) if value else (previous.resilio_version if previous else None)

    async def _async_get_performance_warnings(
        self, previous: ResilioFolderStatus | None
    ) -> tuple[str, ...]:
        """Fetch Resilio's own degraded-state warnings, same fallback rules as above."""
        try:
            payload = await self._client.async_get_performance_warnings()
        except ResilioApiError:
            return previous.performance_warnings if previous else ()
        warnings = payload.get("warnings")
        if not isinstance(warnings, list):
            return previous.performance_warnings if previous else ()
        return tuple(str(warning) for warning in warnings)

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
