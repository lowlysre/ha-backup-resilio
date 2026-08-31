"""Store for tar+json sidecar backups in a Resilio-synced directory, with no HA dependency.

Home Assistant's backup integration protocol expects an agent that can list,
create, download, and delete opaque archives identified by a ``backup_id``.
``custom_components/resilio_backup``'s agent implements that against a plain
directory: each backup is a ``<backup_id>.tar`` archive plus a
``<backup_id>.json`` metadata sidecar. That on-disk convention has no real
Home Assistant dependency beyond the exact shape of the metadata (HA's
``AgentBackup`` model), so this module treats metadata as an opaque JSON
object instead, which keeps it directly testable -- and drivable via the
``resilio-backup-store`` CLI -- against a real directory (including one a
live Resilio Sync agent is actively syncing) without a Home Assistant
install.

Every method here does blocking file I/O. Callers running on an event loop
(Home Assistant included) should invoke them via an executor.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

CHUNK_SIZE = 2**20


class BackupStoreError(Exception):
    """Base error for backup store file operations."""


class BackupNotFoundError(BackupStoreError):
    """Raised when a requested backup id has no matching tar file on disk."""

    def __init__(self, backup_id: str) -> None:
        """Initialize with the missing backup id."""
        super().__init__(f"Backup not found: {backup_id}")
        self.backup_id = backup_id


def parse_backup_date(date_value: str) -> datetime:
    """Parse an ISO-8601 backup date, returning datetime.min for unparsable values.

    Keeps sorting well-defined even for a corrupt or missing ``date`` field:
    unparsable backups sort as the oldest, rather than raising.
    """
    try:
        return datetime.fromisoformat(str(date_value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.min


class BackupStore:
    """Read and write tar+json sidecar backups in a directory."""

    def __init__(self, backup_dir: Path | str) -> None:
        """Initialize the store for a directory of tar+json sidecar backups."""
        self.backup_dir = Path(backup_dir)

    def tar_path(self, backup_id: str) -> Path:
        """Return the tar archive path for a backup id."""
        return self.backup_dir / f"{backup_id}.tar"

    def metadata_path(self, backup_id: str) -> Path:
        """Return the metadata sidecar path for a backup id."""
        return self.backup_dir / f"{backup_id}.json"

    def _load_metadata(self, metadata_path: Path) -> dict[str, Any] | None:
        """Load one metadata sidecar, or None if it's corrupt or missing its archive."""
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as err:
            _LOGGER.warning("Unable to read backup metadata %s: %s", metadata_path, err)
            return None
        if not isinstance(metadata, dict) or not metadata.get("backup_id"):
            _LOGGER.warning("Skipping backup metadata without a backup_id: %s", metadata_path)
            return None
        if not metadata_path.with_suffix(".tar").exists():
            _LOGGER.warning("Skipping stale backup metadata without archive: %s", metadata_path)
            return None
        return metadata

    def list_backups(self) -> list[dict[str, Any]]:
        """Return metadata for every backup with a matching tar file.

        Corrupt or stale sidecars (unreadable JSON, missing ``backup_id``, or
        no matching ``.tar``) are skipped rather than raised, matching what a
        Resilio-synced directory can transiently look like mid-sync.
        """
        if not self.backup_dir.exists():
            return []
        backups = []
        for metadata_path in sorted(self.backup_dir.glob("*.json")):
            metadata = self._load_metadata(metadata_path)
            if metadata is not None:
                backups.append(metadata)
        return backups

    def get_backup(self, backup_id: str) -> dict[str, Any]:
        """Return one backup's metadata, or raise BackupNotFoundError."""
        for backup in self.list_backups():
            if backup.get("backup_id") == backup_id:
                return backup
        raise BackupNotFoundError(backup_id)

    def create_backup(
        self,
        backup_id: str,
        metadata: dict[str, Any],
        chunks: Iterator[bytes],
        *,
        on_progress: Callable[[int], None] | None = None,
    ) -> None:
        """Write `chunks` as `<backup_id>.tar` and `metadata` as its sidecar.

        Rolls back both files on any I/O failure, so a partially written
        backup is never left looking valid to `list_backups`.
        """
        tar_path = self.tar_path(backup_id)
        metadata_path = self.metadata_path(backup_id)
        handle = None
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            handle = tar_path.open("wb")
            bytes_written = 0
            for chunk in chunks:
                handle.write(chunk)
                bytes_written += len(chunk)
                if on_progress is not None:
                    on_progress(bytes_written)
            handle.close()
            handle = None
            metadata_path.write_text(
                json.dumps({**metadata, "backup_id": backup_id}), encoding="utf-8"
            )
        except OSError:
            if handle is not None:
                handle.close()
            tar_path.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            raise

    def read_backup(self, backup_id: str, chunk_size: int = CHUNK_SIZE) -> Iterator[bytes]:
        """Yield a backup's tar contents in chunks, or raise BackupNotFoundError."""
        tar_path = self.tar_path(backup_id)
        if not tar_path.exists():
            raise BackupNotFoundError(backup_id)

        def _iterate() -> Iterator[bytes]:
            with tar_path.open("rb") as handle:
                while chunk := handle.read(chunk_size):
                    yield chunk

        return _iterate()

    def delete_backup(self, backup_id: str) -> None:
        """Delete a backup's tar and metadata sidecar, or raise BackupNotFoundError."""
        tar_path = self.tar_path(backup_id)
        if not tar_path.exists():
            raise BackupNotFoundError(backup_id)
        tar_path.unlink()
        self.metadata_path(backup_id).unlink(missing_ok=True)

    def prune_backups(self, max_backups: int) -> list[str]:
        """Delete all but the `max_backups` most recent backups; return deleted ids.

        Backups are ranked newest-first by metadata `date`. `max_backups <= 0`
        is a no-op (treated as "unlimited"), so callers can disable pruning
        without special-casing zero themselves.
        """
        if max_backups <= 0:
            return []
        backups = sorted(
            self.list_backups(),
            key=lambda backup: parse_backup_date(backup.get("date", "")),
            reverse=True,
        )
        deleted = []
        for backup in backups[max_backups:]:
            backup_id = backup["backup_id"]
            self.delete_backup(backup_id)
            deleted.append(backup_id)
        return deleted
