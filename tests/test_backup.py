"""Tests for the Resilio backup agent."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, call, patch

import pytest

from homeassistant.components.backup.models import BackupAgentError, BackupNotFound

from custom_components.resilio_backup.backup import (
    ResilioBackupAgent,
    _parse_backup_date,
    async_get_backup_agents,
    async_prune_backups,
    async_register_backup_agents_listener,
)
from custom_components.resilio_backup.const import (
    CONF_MAX_BACKUPS,
    CONF_PRUNE_ENABLED,
    DOMAIN,
    SERVICE_PRUNE_BACKUPS,
)
from tests.common import build_agent_backup, build_backup_dir, build_mock_entry, setup_integration


async def _open_stream(chunks: list[bytes]):
    async def _iterator():
        for chunk in chunks:
            yield chunk

    return _iterator()


async def test_backup_round_trip(hass) -> None:
    """Upload, list, fetch, download, and delete a backup."""
    entry = build_mock_entry(hass)
    agent = ResilioBackupAgent(hass, entry)
    backup = build_agent_backup()
    progress = Mock()

    await agent.async_upload_backup(
        open_stream=lambda: _open_stream([b"abc", b"def"]),
        backup=backup,
        on_progress=progress,
    )

    backups = await agent.async_list_backups()
    assert [item.backup_id for item in backups] == ["backup1"]
    assert await agent.async_get_backup("backup1") == backup
    assert b"".join([chunk async for chunk in await agent.async_download_backup("backup1")]) == b"abcdef"

    await agent.async_delete_backup("backup1")

    assert await agent.async_list_backups() == []
    assert progress.call_args_list == [call(bytes_uploaded=3), call(bytes_uploaded=6)]


async def test_list_skips_corrupt_sidecars(hass) -> None:
    """Corrupt metadata files are skipped."""
    backup_dir = build_backup_dir(hass, "corrupt_backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / "broken.json").write_text("{not json", encoding="utf-8")
    entry = build_mock_entry(hass, backup_path=str(backup_dir))
    agent = ResilioBackupAgent(hass, entry)

    assert await agent.async_list_backups() == []


async def test_stale_metadata_is_ignored(hass) -> None:
    """Metadata without a tar file is ignored."""
    backup_dir = build_backup_dir(hass, "stale_backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = build_agent_backup()
    (backup_dir / "backup1.json").write_text(json.dumps(backup.as_dict()), encoding="utf-8")
    entry = build_mock_entry(hass, backup_path=str(backup_dir))
    agent = ResilioBackupAgent(hass, entry)

    assert await agent.async_list_backups() == []
    with pytest.raises(BackupNotFound):
        await agent.async_get_backup("backup1")
    with pytest.raises(BackupNotFound):
        await agent.async_delete_backup("backup1")
    with pytest.raises(BackupNotFound):
        await agent.async_download_backup("backup1")


async def test_missing_backup_raises_not_found(hass) -> None:
    """Missing backups raise BackupNotFound."""
    entry = build_mock_entry(hass)
    agent = ResilioBackupAgent(hass, entry)

    with pytest.raises(BackupNotFound):
        await agent.async_get_backup("missing")
    with pytest.raises(BackupNotFound):
        await agent.async_delete_backup("missing")
    with pytest.raises(BackupNotFound):
        await agent.async_download_backup("missing")


async def test_missing_backup_after_nonmatching_entry_raises_not_found(hass) -> None:
    """A missing id still raises when other backups exist."""
    entry = build_mock_entry(hass)
    agent = ResilioBackupAgent(hass, entry)
    await agent.async_upload_backup(
        open_stream=lambda: _open_stream([b"abc"]),
        backup=build_agent_backup("present"),
        on_progress=lambda **kwargs: None,
    )

    with pytest.raises(BackupNotFound):
        await agent.async_get_backup("missing")


async def test_upload_wraps_filesystem_errors(hass) -> None:
    """Filesystem failures surface as BackupAgentError."""
    entry = build_mock_entry(hass)
    agent = ResilioBackupAgent(hass, entry)
    backup = build_agent_backup()

    with (
        patch.object(Path, "open", side_effect=OSError("boom")),
        pytest.raises(BackupAgentError),
    ):
        await agent.async_upload_backup(
            open_stream=lambda: _open_stream([b"abc"]),
            backup=backup,
            on_progress=lambda **kwargs: None,
        )


async def test_upload_closes_open_file_on_write_failure(hass) -> None:
    """Write failures close the open handle before raising."""
    entry = build_mock_entry(hass)
    agent = ResilioBackupAgent(hass, entry)
    backup = build_agent_backup()

    class BrokenHandle:
        """File handle that fails on write."""

        def __init__(self) -> None:
            """Initialize the fake file handle."""
            self.closed = False

        def write(self, _chunk: bytes) -> int:
            """Raise a write failure."""
            raise OSError("boom")

        def close(self) -> None:
            """Mark the handle as closed."""
            self.closed = True

    handle = BrokenHandle()

    with (
        patch.object(Path, "open", return_value=handle),
        pytest.raises(BackupAgentError),
    ):
        await agent.async_upload_backup(
            open_stream=lambda: _open_stream([b"abc"]),
            backup=backup,
            on_progress=lambda **kwargs: None,
        )

    assert handle.closed is True


async def test_delete_wraps_filesystem_errors(hass) -> None:
    """Delete failures surface as BackupAgentError."""
    entry = build_mock_entry(hass)
    agent = ResilioBackupAgent(hass, entry)
    await agent.async_upload_backup(
        open_stream=lambda: _open_stream([b"abc"]),
        backup=build_agent_backup(),
        on_progress=lambda **kwargs: None,
    )

    with patch.object(Path, "unlink", side_effect=OSError("boom")):
        with pytest.raises(BackupAgentError):
            await agent.async_delete_backup("backup1")


def test_parse_backup_date_invalid_returns_min() -> None:
    """Invalid dates sort as the oldest possible value."""
    assert _parse_backup_date("not-a-date") == _parse_backup_date("0001-01-01T00:00:00")


async def test_pruning_deletes_oldest_first(hass) -> None:
    """Pruning keeps the newest configured backups."""
    entry = build_mock_entry(
        hass, options={CONF_PRUNE_ENABLED: True, CONF_MAX_BACKUPS: 0}
    )
    agent = ResilioBackupAgent(hass, entry)

    for backup in (
        build_agent_backup("backup1", date="2026-08-30T23:00:00+00:00"),
        build_agent_backup("backup2", date="2026-08-30T23:10:00+00:00"),
        build_agent_backup("backup3", date="2026-08-30T23:20:00+00:00"),
    ):
        await agent.async_upload_backup(
            open_stream=lambda backup_id=backup.backup_id: _open_stream([backup_id.encode()]),
            backup=backup,
            on_progress=lambda **kwargs: None,
        )

    pruning_entry = build_mock_entry(
        hass,
        backup_path=entry.data["backup_path"],
        options={CONF_PRUNE_ENABLED: True, CONF_MAX_BACKUPS: 2},
    )

    assert await async_prune_backups(hass, pruning_entry) == 1
    assert sorted(backup.backup_id for backup in await agent.async_list_backups()) == [
        "backup2",
        "backup3",
    ]


async def test_pruning_respects_disabled_flag(hass) -> None:
    """Pruning can be disabled."""
    entry = build_mock_entry(
        hass, options={CONF_PRUNE_ENABLED: False, CONF_MAX_BACKUPS: 1}
    )
    assert await async_prune_backups(hass, entry) == 0


async def test_pruning_respects_unlimited_setting(hass) -> None:
    """Zero means keep everything."""
    entry = build_mock_entry(
        hass, options={CONF_PRUNE_ENABLED: True, CONF_MAX_BACKUPS: 0}
    )
    assert await async_prune_backups(hass, entry) == 0


async def test_prune_service_end_to_end(hass, aioclient_mock) -> None:
    """The prune service applies to loaded entries."""
    entry = await setup_integration(
        hass,
        aioclient_mock,
        options={CONF_PRUNE_ENABLED: True, CONF_MAX_BACKUPS: 1},
    )
    agent = ResilioBackupAgent(hass, entry)

    await agent.async_upload_backup(
        open_stream=lambda: _open_stream([b"older"]),
        backup=build_agent_backup("older", date="2026-08-30T22:00:00+00:00"),
        on_progress=lambda **kwargs: None,
    )
    await agent.async_upload_backup(
        open_stream=lambda: _open_stream([b"newer"]),
        backup=build_agent_backup("newer", date="2026-08-30T23:00:00+00:00"),
        on_progress=lambda **kwargs: None,
    )

    await hass.services.async_call(DOMAIN, SERVICE_PRUNE_BACKUPS, blocking=True)

    assert [backup.backup_id for backup in await agent.async_list_backups()] == ["newer"]


async def test_backup_agent_listeners_on_setup_and_unload(hass, aioclient_mock) -> None:
    """Backup listeners are notified when entries change."""
    listener = Mock()
    remove = async_register_backup_agents_listener(hass, listener=listener)

    entry = await setup_integration(hass, aioclient_mock)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert listener.call_count == 2
    remove()


async def test_async_get_backup_agents_only_returns_loaded_entries(hass, aioclient_mock) -> None:
    """Only loaded entries are exposed as backup agents."""
    entry = await setup_integration(hass, aioclient_mock)
    agents = await async_get_backup_agents(hass)

    assert len(agents) == 1
    assert agents[0].unique_id == entry.entry_id
