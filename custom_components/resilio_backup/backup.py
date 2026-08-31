"""Backup agent support for Resilio Backup."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.components.backup.agent import BackupAgent, OnProgressCallback
from homeassistant.components.backup.models import AgentBackup, BackupAgentError, BackupNotFound
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_BACKUP_PATH,
    CONF_MAX_BACKUPS,
    CONF_PRUNE_ENABLED,
    DEFAULT_MAX_BACKUPS,
    DEFAULT_PRUNE_ENABLED,
    DOMAIN,
    EVENT_BACKUPS_PRUNED,
)

LOGGER = logging.getLogger(__name__)
LISTENERS_KEY = f"{DOMAIN}_backup_listeners"
CHUNK_SIZE = 2**20


async def async_get_backup_agents(
    hass: HomeAssistant,
    **_kwargs: Any,
) -> list[BackupAgent]:
    """Return backup agents for all loaded entries."""
    return [
        ResilioBackupAgent(hass, entry)
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]


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


def _parse_backup_date(date_value: str) -> datetime:
    """Parse a backup date into a sortable datetime."""
    try:
        return datetime.fromisoformat(date_value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min


def _load_metadata_file(metadata_path: Path) -> AgentBackup | None:
    """Load one backup sidecar file from disk."""
    try:
        backup = AgentBackup.from_dict(json.loads(metadata_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as err:
        LOGGER.warning("Unable to read backup metadata %s: %s", metadata_path, err)
        return None

    tar_path = metadata_path.with_suffix(".tar")
    if not tar_path.exists():
        LOGGER.warning("Skipping stale backup metadata without archive: %s", metadata_path)
        return None
    return backup


class ResilioBackupAgent(BackupAgent):
    """Backup agent backed by a Resilio-managed directory."""

    domain = DOMAIN

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the agent."""
        self.name = entry.title
        self.unique_id = entry.entry_id
        self._hass = hass
        self._entry = entry
        self._backup_dir = Path(entry.data[CONF_BACKUP_PATH])

    def _get_tar_path(self, backup_id: str) -> Path:
        """Return the tar path for a backup id."""
        return self._backup_dir / f"{backup_id}.tar"

    def _get_metadata_path(self, backup_id: str) -> Path:
        """Return the metadata path for a backup id."""
        return self._backup_dir / f"{backup_id}.json"

    async def async_list_backups(self, **kwargs: Any) -> list[AgentBackup]:
        """List available backups."""
        metadata_paths = await self._hass.async_add_executor_job(
            lambda: list(self._backup_dir.glob("*.json"))
        )
        backups: list[AgentBackup] = []
        for metadata_path in metadata_paths:
            backup = await self._hass.async_add_executor_job(_load_metadata_file, metadata_path)
            if backup is not None:
                backups.append(backup)
        return backups

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
        tar_path = self._get_tar_path(backup.backup_id)
        metadata_path = self._get_metadata_path(backup.backup_id)
        file_handle = None
        bytes_uploaded = 0

        try:
            await self._hass.async_add_executor_job(
                lambda: self._backup_dir.mkdir(parents=True, exist_ok=True)
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
        tar_path = self._get_tar_path(backup_id)
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
        tar_path = self._get_tar_path(backup_id)
        metadata_path = self._get_metadata_path(backup_id)
        if not await self._hass.async_add_executor_job(tar_path.exists):
            raise BackupNotFound(
                translation_domain=DOMAIN,
                translation_key="backup_not_found",
                translation_placeholders={"backup_id": backup_id},
            )

        try:
            await self._hass.async_add_executor_job(tar_path.unlink)
            await self._hass.async_add_executor_job(
                lambda: metadata_path.unlink(missing_ok=True)
            )
        except OSError as err:
            raise BackupAgentError(
                translation_domain=DOMAIN,
                translation_key="delete_backup_failed",
                translation_placeholders={"backup_id": backup_id},
            ) from err


async def async_prune_backups(hass: HomeAssistant, entry: ConfigEntry) -> int:
    """Prune old backups for one entry."""
    if not entry.options.get(CONF_PRUNE_ENABLED, DEFAULT_PRUNE_ENABLED):
        return 0

    max_backups = entry.options.get(CONF_MAX_BACKUPS, DEFAULT_MAX_BACKUPS)
    if max_backups == 0:
        return 0

    agent = ResilioBackupAgent(hass, entry)
    backups = sorted(
        await agent.async_list_backups(),
        key=lambda backup: _parse_backup_date(backup.date),
        reverse=True,
    )

    deleted = 0
    for backup in backups[max_backups:]:
        await agent.async_delete_backup(backup.backup_id)
        deleted += 1

    if deleted:
        hass.bus.async_fire(
            EVENT_BACKUPS_PRUNED,
            {"entry_id": entry.entry_id, "deleted": deleted},
        )
    return deleted
