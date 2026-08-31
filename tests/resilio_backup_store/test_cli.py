"""Tests for the resilio_backup_store CLI."""

from __future__ import annotations

import io
import json

import pytest

from custom_components.resilio_backup.resilio_backup_store import cli


def test_requires_command() -> None:
    """Omitting a subcommand is a usage error."""
    with pytest.raises(SystemExit):
        cli.main([])


def test_create_and_list_round_trip(tmp_path, capsys) -> None:
    """A created backup shows up in the list output."""
    tar_path = tmp_path / "archive.tar"
    tar_path.write_bytes(b"abcdef")
    backup_dir = tmp_path / "backups"

    exit_code = cli.main(
        [
            "create",
            "--backup-path", str(backup_dir),
            "--backup-id", "backup1",
            "--metadata", json.dumps({"date": "2026-08-30T23:00:00+00:00", "name": "Nightly"}),
            "--input", str(tar_path),
        ]
    )
    assert exit_code == 0
    created = json.loads(capsys.readouterr().out)
    assert created == {
        "backup_id": "backup1",
        "date": "2026-08-30T23:00:00+00:00",
        "name": "Nightly",
    }

    exit_code = cli.main(["list", "--backup-path", str(backup_dir)])
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == [created]


def test_create_from_stdin(tmp_path, capsys, monkeypatch) -> None:
    """Omitting --input reads the archive from stdin."""
    monkeypatch.setattr("sys.stdin", type("_Stdin", (), {"buffer": io.BytesIO(b"abc")})())
    backup_dir = tmp_path / "backups"

    exit_code = cli.main(
        ["create", "--backup-path", str(backup_dir), "--backup-id", "backup1"]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["backup_id"] == "backup1"
    assert (backup_dir / "backup1.tar").read_bytes() == b"abc"


def test_restore_writes_output_file(tmp_path) -> None:
    """The restore command writes the archive bytes to --output."""
    backup_dir = tmp_path / "backups"
    cli.main(
        [
            "create",
            "--backup-path", str(backup_dir),
            "--backup-id", "backup1",
            "--input", str(_write_tar(tmp_path, b"abcdef")),
        ]
    )
    output_path = tmp_path / "restored.tar"

    exit_code = cli.main(
        [
            "restore",
            "--backup-path", str(backup_dir),
            "--backup-id", "backup1",
            "--output", str(output_path),
        ]
    )

    assert exit_code == 0
    assert output_path.read_bytes() == b"abcdef"


def test_delete_removes_backup(tmp_path) -> None:
    """The delete command removes both the tar and metadata sidecar."""
    backup_dir = tmp_path / "backups"
    cli.main(
        [
            "create",
            "--backup-path", str(backup_dir),
            "--backup-id", "backup1",
            "--input", str(_write_tar(tmp_path, b"abc")),
        ]
    )

    exit_code = cli.main(
        ["delete", "--backup-path", str(backup_dir), "--backup-id", "backup1"]
    )

    assert exit_code == 0
    assert not (backup_dir / "backup1.tar").exists()
    assert not (backup_dir / "backup1.json").exists()


def test_prune_command_prints_deleted_ids(tmp_path, capsys) -> None:
    """The prune command reports which backup ids were deleted."""
    backup_dir = tmp_path / "backups"
    for backup_id, date in (
        ("backup1", "2026-08-30T23:00:00+00:00"),
        ("backup2", "2026-08-30T23:10:00+00:00"),
    ):
        cli.main(
            [
                "create",
                "--backup-path", str(backup_dir),
                "--backup-id", backup_id,
                "--metadata", json.dumps({"date": date}),
                "--input", str(_write_tar(tmp_path, backup_id.encode(), name=f"{backup_id}.tar")),
            ]
        )
        capsys.readouterr()

    exit_code = cli.main(
        ["prune", "--backup-path", str(backup_dir), "--max-backups", "1"]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"deleted": ["backup1"]}


def test_missing_backup_exits_non_zero(tmp_path, capsys) -> None:
    """Operating on a missing backup id reports the error and exits non-zero."""
    exit_code = cli.main(
        ["delete", "--backup-path", str(tmp_path), "--backup-id", "missing"]
    )

    assert exit_code == 1
    assert "missing" in capsys.readouterr().err


def _write_tar(tmp_path, content: bytes, *, name: str = "archive.tar"):
    """Write a small standalone archive file for CLI --input arguments."""
    path = tmp_path / name
    path.write_bytes(content)
    return path
