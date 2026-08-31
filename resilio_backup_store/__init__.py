"""HA-agnostic file store for tar+json sidecar backups in a Resilio-synced directory.

This package has no dependency on Home Assistant: it only needs a directory
path. ``custom_components/resilio_backup/backup.py``'s ``ResilioBackupAgent``
wraps ``BackupStore`` to add Home Assistant's ``AgentBackup``/executor-job
semantics; the ``resilio_backup_store.cli`` module drives it directly, so the
same list/create/restore/delete/prune logic can be exercised as a standalone
CLI or in CI against a real directory, without a Home Assistant install.
"""

from .store import BackupNotFoundError, BackupStore, BackupStoreError

__all__ = [
    "BackupNotFoundError",
    "BackupStore",
    "BackupStoreError",
]
