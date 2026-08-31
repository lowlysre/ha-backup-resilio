"""Tests for the resilio_client CLI."""

from __future__ import annotations

import json

import pytest

from resilio_client import cli
from resilio_client.client import ResilioApiError

CONNECTION_ARGS = [
    "--host", "resilio.local",
    "--port", "8888",
    "--username", "admin",
    "--password", "secret",
]

MOCK_OS = {"os": "windows", "version": "3.0", "status": 200}
MOCK_FOLDERS = [{"id": "folder123", "path": "/mnt/sync/folders/backups"}]


@pytest.fixture(name="mock_client")
def fixture_mock_client(monkeypatch):
    """Patch ResilioClient construction to return a stub with canned responses."""

    class _StubClient:
        """Fake ResilioClient with canned async responses for CLI tests."""

        def __init__(self, *_args, **_kwargs):
            """Ignore constructor arguments; this stub is response-only."""

        async def async_get_os(self):
            """Return canned OS info."""
            return MOCK_OS

        async def async_get_folders(self):
            """Return canned folders."""
            return MOCK_FOLDERS

        async def async_add_folder(self, path):
            """Return a canned created-folder response."""
            return {"id": "new-folder", "path": path}

        async def async_get_share_link(self, folder_id, name, *, permission, timelimit):
            """Return a canned share link."""
            del folder_id, name, permission, timelimit
            return "https://link.resilio.com/#f=test"

    monkeypatch.setattr(cli, "ResilioClient", _StubClient)
    return _StubClient


def test_status_command_prints_json(mock_client, capsys) -> None:
    """The status command prints the OS info as JSON."""
    del mock_client
    exit_code = cli.main(["status", *CONNECTION_ARGS])
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == MOCK_OS


def test_folders_command_prints_json(mock_client, capsys) -> None:
    """The folders command prints the folder list as JSON."""
    del mock_client
    exit_code = cli.main(["folders", *CONNECTION_ARGS])
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == MOCK_FOLDERS


def test_add_folder_command_prints_json(mock_client, capsys) -> None:
    """The add-folder command prints the created folder as JSON."""
    del mock_client
    exit_code = cli.main(["add-folder", *CONNECTION_ARGS, "--path", "/mnt/sync/folders/new"])
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "id": "new-folder",
        "path": "/mnt/sync/folders/new",
    }


def test_share_link_command_prints_json(mock_client, capsys) -> None:
    """The share-link command prints the generated link as JSON."""
    del mock_client
    exit_code = cli.main(
        ["share-link", *CONNECTION_ARGS, "--folder-id", "folder123", "--name", "backups"]
    )
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"link": "https://link.resilio.com/#f=test"}


def test_api_error_exits_non_zero(monkeypatch, capsys) -> None:
    """A ResilioApiError from the client is reported on stderr with exit code 1."""

    class _FailingClient:  # pylint: disable=too-few-public-methods
        """Fake ResilioClient whose status check always raises."""

        def __init__(self, *_args, **_kwargs):
            """Ignore constructor arguments; this stub is response-only."""

        async def async_get_os(self):
            """Always raise a Resilio API error."""
            raise ResilioApiError("boom")

    monkeypatch.setattr(cli, "ResilioClient", _FailingClient)
    exit_code = cli.main(["status", *CONNECTION_ARGS])
    assert exit_code == 1
    assert "boom" in capsys.readouterr().err


def test_requires_command() -> None:
    """Omitting a subcommand is a usage error."""
    with pytest.raises(SystemExit):
        cli.main([])
