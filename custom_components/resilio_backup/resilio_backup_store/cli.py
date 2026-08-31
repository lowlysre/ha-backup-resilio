"""Command-line interface for the local tar+json sidecar backup store.

Exposes the same file operations ``custom_components/resilio_backup/backup.py``'s
``ResilioBackupAgent`` performs against a Resilio-synced directory --
create, list, restore, delete, prune -- as standalone, scriptable commands,
so that logic can be exercised directly against a real directory (manually,
or in CI against a folder a live Resilio Sync agent is actually syncing)
without a Home Assistant install.

Usage::

    resilio-backup-store create --backup-path ./backups --backup-id b1 \\
        --metadata '{"date": "2026-08-30T23:00:00+00:00"}' --input archive.tar
    resilio-backup-store list --backup-path ./backups
    resilio-backup-store restore --backup-path ./backups --backup-id b1 --output restored.tar
    resilio-backup-store delete --backup-path ./backups --backup-id b1
    resilio-backup-store prune --backup-path ./backups --max-backups 7

Every command prints its result as JSON on stdout (``restore`` instead writes
the raw archive bytes to ``--output``, or stdout if omitted) and exits
non-zero with an error message on stderr on failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, BinaryIO

from .store import CHUNK_SIZE, BackupStore, BackupStoreError


def _read_chunks(handle: BinaryIO, chunk_size: int = CHUNK_SIZE):
    """Yield fixed-size chunks from a binary file handle until EOF."""
    while chunk := handle.read(chunk_size):
        yield chunk


def _load_metadata(args: argparse.Namespace) -> dict[str, Any]:
    """Load backup metadata from --metadata-file or --metadata, defaulting to {}."""
    if args.metadata_file:
        with open(args.metadata_file, encoding="utf-8") as handle:
            return json.load(handle)
    if args.metadata:
        return json.loads(args.metadata)
    return {}


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="resilio-backup-store",
        description="Manage tar+json sidecar backups in a Resilio-synced directory",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_cmd = subparsers.add_parser("list", help="List backups in a directory")
    list_cmd.add_argument("--backup-path", required=True, help="Backup directory")

    create_cmd = subparsers.add_parser("create", help="Create a backup from a tar file or stdin")
    create_cmd.add_argument("--backup-path", required=True, help="Backup directory")
    create_cmd.add_argument("--backup-id", required=True, help="Backup id")
    create_cmd.add_argument(
        "--input", default="-", help="Tar file to copy in, or '-' for stdin (default: stdin)"
    )
    create_cmd.add_argument("--metadata", help="Backup metadata as a JSON object")
    create_cmd.add_argument("--metadata-file", help="Path to a JSON file with backup metadata")

    restore_cmd = subparsers.add_parser("restore", help="Write a backup's tar contents out")
    restore_cmd.add_argument("--backup-path", required=True, help="Backup directory")
    restore_cmd.add_argument("--backup-id", required=True, help="Backup id")
    restore_cmd.add_argument(
        "--output", default="-", help="Path to write the tar contents to, or '-' for stdout"
    )

    delete_cmd = subparsers.add_parser("delete", help="Delete a backup")
    delete_cmd.add_argument("--backup-path", required=True, help="Backup directory")
    delete_cmd.add_argument("--backup-id", required=True, help="Backup id")

    prune_cmd = subparsers.add_parser("prune", help="Delete all but the N most recent backups")
    prune_cmd.add_argument("--backup-path", required=True, help="Backup directory")
    prune_cmd.add_argument("--max-backups", required=True, type=int, help="Backups to keep")

    return parser


def _run(args: argparse.Namespace) -> Any:
    """Dispatch to the requested command and return its JSON-able result, if any."""
    store = BackupStore(args.backup_path)
    if args.command == "list":
        return store.list_backups()
    if args.command == "create":
        metadata = _load_metadata(args)
        if args.input == "-":
            store.create_backup(args.backup_id, metadata, _read_chunks(sys.stdin.buffer))
        else:
            with open(args.input, "rb") as handle:
                store.create_backup(args.backup_id, metadata, _read_chunks(handle))
        return store.get_backup(args.backup_id)
    if args.command == "restore":
        chunks = store.read_backup(args.backup_id)
        if args.output == "-":
            for chunk in chunks:
                sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
        else:
            with open(args.output, "wb") as handle:
                for chunk in chunks:
                    handle.write(chunk)
        return None
    if args.command == "delete":
        store.delete_backup(args.backup_id)
        return None
    if args.command == "prune":
        return {"deleted": store.prune_backups(args.max_backups)}
    raise ValueError(f"Unknown command: {args.command}")  # pragma: no cover - argparse guards this


def main(argv: list[str] | None = None) -> int:
    """Run the CLI, returning a process exit code."""
    args = _build_parser().parse_args(argv)
    try:
        result = _run(args)
    except BackupStoreError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    if result is not None:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
