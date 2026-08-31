"""Command-line interface for the Resilio Sync WebUI API client.

Exposes the same requests ``custom_components/resilio_backup`` makes against
a Resilio Sync agent as standalone, scriptable commands, so the connection
and folder-management logic can be exercised directly against a live
container (manually, or in CI) without a Home Assistant install.

Usage::

    resilio-client status --host localhost --port 8888 --username admin --password secret
    resilio-client folders --host localhost --port 8888 --username admin --password secret
    resilio-client add-folder --host ... --path /mnt/sync/folders/backups
    resilio-client share-link --host ... --folder-id 1a2b3c --name backups

Every command prints its result as JSON on stdout and exits non-zero with an
error message on stderr on failure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import aiohttp

from .client import ResilioApiError, ResilioClient


def _add_connection_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the connection flags shared by every subcommand."""
    parser.add_argument("--host", required=True, help="Resilio Sync WebUI host")
    parser.add_argument("--port", required=True, type=int, help="Resilio Sync WebUI port")
    parser.add_argument("--username", required=True, help="Resilio Sync WebUI username")
    parser.add_argument("--password", required=True, help="Resilio Sync WebUI password")
    parser.add_argument("--ssl", action="store_true", help="Connect over HTTPS")
    parser.add_argument(
        "--no-verify-ssl",
        dest="verify_ssl",
        action="store_false",
        default=True,
        help="Skip TLS certificate verification (only meaningful with --ssl)",
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="resilio-client", description="Resilio Sync WebUI API client"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Check connectivity and print system info")
    _add_connection_arguments(status)

    folders = subparsers.add_parser("folders", help="List managed Resilio folders")
    _add_connection_arguments(folders)

    add_folder = subparsers.add_parser("add-folder", help="Create a new Resilio folder")
    _add_connection_arguments(add_folder)
    add_folder.add_argument("--path", required=True, help="Path for the new folder")

    share_link = subparsers.add_parser("share-link", help="Generate a peer-invite link")
    _add_connection_arguments(share_link)
    share_link.add_argument("--folder-id", required=True, help="Resilio folder id")
    share_link.add_argument("--name", required=True, help="Folder name for the invite link")
    share_link.add_argument(
        "--permission",
        type=int,
        default=3,
        help="Resilio permission level: 2=read-only, 3=read-write, 4=owner (default: 3)",
    )
    share_link.add_argument(
        "--timelimit",
        type=int,
        default=7 * 24 * 3600,
        help="Link validity in seconds (default: 7 days)",
    )

    return parser


async def _async_run(args: argparse.Namespace) -> Any:
    """Dispatch to the requested command and return its JSON-able result."""
    async with aiohttp.ClientSession() as session:
        client = ResilioClient(
            session,
            args.host,
            args.port,
            args.username,
            args.password,
            args.ssl,
            args.verify_ssl,
        )
        if args.command == "status":
            return await client.async_get_os()
        if args.command == "folders":
            return await client.async_get_folders()
        if args.command == "add-folder":
            return await client.async_add_folder(args.path)
        if args.command == "share-link":
            link = await client.async_get_share_link(
                args.folder_id,
                args.name,
                permission=args.permission,
                timelimit=args.timelimit,
            )
            return {"link": link}
        raise ValueError(f"Unknown command: {args.command}")  # pragma: no cover - argparse guards this


def main(argv: list[str] | None = None) -> int:
    """Run the CLI, returning a process exit code."""
    args = _build_parser().parse_args(argv)
    try:
        result = asyncio.run(_async_run(args))
    except ResilioApiError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
