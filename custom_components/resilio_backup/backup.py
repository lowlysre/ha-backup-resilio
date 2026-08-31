"""Backup agent support for Resilio Backup.

The tar+json sidecar file management this agent needs -- list, create,
download, delete, prune -- has no real Home Assistant dependency beyond the
exact shape of ``AgentBackup``'s metadata, so that logic lives in the
HA-agnostic ``resilio_backup_store`` package (also drivable as the
``resilio-backup-store`` CLI, including in CI against a real directory).
This module only adds the Home Assistant-specific pieces: ``AgentBackup``
(de)serialization, translated errors, and running blocking file I/O via
``hass.async_add_executor_job``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
import json
import logging
from typing import Any

from homeassistant.components.backup.agent import BackupAgent, OnProgressCallback
from homeassistant.components.backup.models import AgentBackup, BackupAgentError, BackupNotFound
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback

from resilio_backup_store import BackupNotFoundError, BackupStore
from resilio_backup_store.store import CHUNK_SIZE, parse_backup_date as _parse_backup_date

from .const import (
    CONF_BACKUP_PATH,
    CONF_MAX_BACKUPS,
    CONF_PRUNE_ENABLED,
    DEFAULT_MAX_BACKUPS,
    DEFAULT_PRUNE_ENABLED,
    DOMAIN,
    EVENT_BACKUPS_PRUNED,
)
from .coordinator import ResilioConfigEntry

LOGGER = logging.getLogger(__name__)
LISTENERS_KEY = f"{DOMAIN}_backup_listeners"

__all__ = [
    "ResilioBackupAgent",
    "_parse_backup_date",
    "async_get_backup_agents",
    "async_notify_backup_listeners",
    "async_prune_backups",
    "async_register_backup_agents_listener",
]


async def async_get_backup_agents(
    hass: HomeAssistant,
    **_kwargs: Any,
) -> list[BackupAgent]:
    """Return backup agents for all loaded entries."""
    agents: list[BackupAgent] = []
    loaded_entry: ResilioConfigEntry
    for loaded_entry in hass.config_entries.async_entries(DOMAIN):
        if loaded_entry.state is ConfigEntryState.LOADED:
            agents.append(ResilioBackupAgent(hass, loaded_entry))
    return agents


@callback
def async_register_backup_agents_listener(
    hass: HomeAssistant,
    *,
    listener: Callable[[], None],
    **_kwargs: Any,
) -> Callable[[], None]:
    """Register a listener for backup agent changes."""
    listeners: list[Callable[[], None]] = hass.data.setdefault(LISTENERS_KEY, [])
    listeners.append(listener)

    @callback
    def _remove_listener() -> None:
        listeners.remove(listener)

    return _remove_listener


@callback
def async_notify_backup_listeners(hass: HomeAssistant) -> None:
    """Notify listeners that backup agents changed."""
    for listener in list(hass.data.get(LISTENERS_KEY, [])):
        listener()


def _backup_from_metadata(metadata: dict[str, Any]) -> AgentBackup | None:
    """Convert one store metadata dict into an AgentBackup, or None if invalid."""
    try:
        return AgentBackup.from_dict(metadata)
    except (KeyError, TypeError, ValueError) as err:
        LOGGER.warning(
            "Unable to parse backup metadata %s: %s", metadata.get("backup_id"), err
        )
        return None


class ResilioBackupAgent(BackupAgent):
    """Backup agent backed by a Resilio-managed directory."""

    domain = DOMAIN

    def __init__(self, hass: HomeAssistant, entry: ResilioConfigEntry) -> None:
        """Initialize the agent."""
        self.name = entry.title
        self.unique_id = entry.entry_id
        self._hass = hass
        self._entry = entry
        self._store = BackupStore(entry.data[CONF_BACKUP_PATH])

    async def async_list_backups(self, **kwargs: Any) -> list[AgentBackup]:
        """List available backups."""
        metadata_list = await self._hass.async_add_executor_job(self._store.list_backups)
        return [
            backup
            for metadata in metadata_list
            if (backup := _backup_from_metadata(metadata)) is not None
        ]

    async def async_get_backup(
        self,
        backup_id: str,
        **kwargs: Any,
    ) -> AgentBackup:
        """Return one backup."""
        for backup in await self.async_list_backups():
            if backup.backup_id == backup_id:
                return backup
        raise BackupNotFound(
            translation_domain=DOMAIN,
            translation_key="backup_not_found",
            translation_placeholders={"backup_id": backup_id},
        )

    async def async_upload_backup(
        self,
        *,
        open_stream: Callable[[], Coroutine[Any, Any, AsyncIterator[bytes]]],
        backup: AgentBackup,
        on_progress: OnProgressCallback,
        **kwargs: Any,
    ) -> None:
        """Upload a backup into the Resilio-managed folder."""
        tar_path = self._store.tar_path(backup.backup_id)
        metadata_path = self._store.metadata_path(backup.backup_id)
        file_handle = None
        bytes_uploaded = 0

        try:
            await self._hass.async_add_executor_job(
                lambda: self._store.backup_dir.mkdir(parents=True, exist_ok=True)
            )
            file_handle = await self._hass.async_add_executor_job(tar_path.open, "wb")
            async for chunk in await open_stream():
                bytes_uploaded += len(chunk)
                await self._hass.async_add_executor_job(file_handle.write, chunk)
                on_progress(bytes_uploaded=bytes_uploaded)
            await self._hass.async_add_executor_job(file_handle.close)
            file_handle = None
            await self._hass.async_add_executor_job(
                lambda: metadata_path.write_text(
                    json.dumps(backup.as_dict()), encoding="utf-8"
                )
            )
            await async_prune_backups(self._hass, self._entry)
        except OSError as err:
            if file_handle is not None:
                await self._hass.async_add_executor_job(file_handle.close)
            await self._hass.async_add_executor_job(lambda: tar_path.unlink(missing_ok=True))
            await self._hass.async_add_executor_job(
                lambda: metadata_path.unlink(missing_ok=True)
            )
            raise BackupAgentError(
                translation_domain=DOMAIN,
                translation_key="upload_backup_failed",
                translation_placeholders={"backup_id": backup.backup_id},
            ) from err

    async def async_download_backup(
        self,
        backup_id: str,
        **kwargs: Any,
    ) -> AsyncIterator[bytes]:
        """Yield backup contents as chunks."""
        tar_path = self._store.tar_path(backup_id)
        if not await self._hass.async_add_executor_job(tar_path.exists):
            raise BackupNotFound(
                translation_domain=DOMAIN,
                translation_key="backup_not_found",
                translation_placeholders={"backup_id": backup_id},
            )

        async def _iterate_file() -> AsyncIterator[bytes]:
            file_handle = await self._hass.async_add_executor_job(tar_path.open, "rb")
            try:
                while True:
                    chunk = await self._hass.async_add_executor_job(
                        file_handle.read, CHUNK_SIZE
                    )
                    if not chunk:
                        break
                    yield chunk
            finally:
                await self._hass.async_add_executor_job(file_handle.close)

        return _iterate_file()

    async def async_delete_backup(self, backup_id: str, **kwargs: Any) -> None:
        """Delete a backup and its metadata."""
        try:
            await self._hass.async_add_executor_job(self._store.delete_backup, backup_id)
        except BackupNotFoundError as err:
            raise BackupNotFound(
                translation_domain=DOMAIN,
                translation_key="backup_not_found",
                translation_placeholders={"backup_id": backup_id},
            ) from err
        except OSError as err:
            raise BackupAgentError(
                translation_domain=DOMAIN,
                translation_key="delete_backup_failed",
                translation_placeholders={"backup_id": backup_id},
            ) from err


async def async_prune_backups(hass: HomeAssistant, entry: ResilioConfigEntry) -> int:
    """Prune old backups for one entry."""
    if not entry.options.get(CONF_PRUNE_ENABLED, DEFAULT_PRUNE_ENABLED):
        return 0

    max_backups = entry.options.get(CONF_MAX_BACKUPS, DEFAULT_MAX_BACKUPS)
    store = BackupStore(entry.data[CONF_BACKUP_PATH])
    deleted = await hass.async_add_executor_job(store.prune_backups, max_backups)

    if deleted:
        hass.bus.async_fire(
            EVENT_BACKUPS_PRUNED,
            {"entry_id": entry.entry_id, "deleted": len(deleted)},
        )
    return len(deleted)
