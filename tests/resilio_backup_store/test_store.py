"""Tests for the tar+json sidecar backup store."""

from __future__ import annotations

import json

import pytest

from resilio_backup_store.store import (
    BackupNotFoundError,
    BackupStore,
    parse_backup_date,
)


def test_list_backups_empty_directory_does_not_raise(tmp_path) -> None:
    """A missing backup directory lists as empty instead of raising."""
    store = BackupStore(tmp_path / "does-not-exist")

    assert not store.list_backups()


def test_create_list_get_read_delete_round_trip(tmp_path) -> None:
    """A backup can be created, listed, fetched, read back, and deleted."""
    store = BackupStore(tmp_path)
    progress: list[int] = []

    store.create_backup(
        "backup1",
        {"date": "2026-08-30T23:00:00+00:00", "name": "Nightly"},
        iter([b"abc", b"def"]),
        on_progress=progress.append,
    )

    assert progress == [3, 6]
    assert [backup["backup_id"] for backup in store.list_backups()] == ["backup1"]
    assert store.get_backup("backup1")["name"] == "Nightly"
    assert b"".join(store.read_backup("backup1")) == b"abcdef"

    store.delete_backup("backup1")

    assert not store.list_backups()


def test_create_persists_backup_id_even_if_metadata_omits_it(tmp_path) -> None:
    """The backup_id passed to create_backup always lands in the sidecar."""
    store = BackupStore(tmp_path)

    store.create_backup("backup1", {"date": "2026-08-30T23:00:00+00:00"}, iter([b"abc"]))

    assert store.get_backup("backup1")["backup_id"] == "backup1"


def test_list_skips_corrupt_sidecar(tmp_path) -> None:
    """Corrupt metadata files are skipped rather than raised."""
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")

    assert not BackupStore(tmp_path).list_backups()


def test_list_skips_sidecar_without_backup_id(tmp_path) -> None:
    """Metadata missing a backup_id is skipped."""
    (tmp_path / "backup1.json").write_text(json.dumps({"date": "x"}), encoding="utf-8")
    (tmp_path / "backup1.tar").write_bytes(b"abc")

    assert not BackupStore(tmp_path).list_backups()


def test_list_skips_stale_metadata_without_archive(tmp_path) -> None:
    """Metadata without a matching tar file is treated as stale."""
    store = BackupStore(tmp_path)
    (tmp_path / "backup1.json").write_text(
        json.dumps({"backup_id": "backup1"}), encoding="utf-8"
    )

    assert not store.list_backups()
    with pytest.raises(BackupNotFoundError):
        store.get_backup("backup1")
    with pytest.raises(BackupNotFoundError):
        store.read_backup("backup1")
    with pytest.raises(BackupNotFoundError):
        store.delete_backup("backup1")


def test_get_missing_backup_raises_not_found(tmp_path) -> None:
    """Fetching a missing backup id raises BackupNotFoundError."""
    with pytest.raises(BackupNotFoundError) as excinfo:
        BackupStore(tmp_path).get_backup("missing")

    assert excinfo.value.backup_id == "missing"


def test_create_rolls_back_on_write_failure(tmp_path) -> None:
    """A write failure mid-stream removes any partial tar/metadata files."""
    store = BackupStore(tmp_path)

    def _failing_chunks():
        yield b"abc"
        raise OSError("boom")

    with pytest.raises(OSError):
        store.create_backup("backup1", {}, _failing_chunks())

    assert not store.tar_path("backup1").exists()
    assert not store.metadata_path("backup1").exists()


def test_prune_keeps_newest_n_backups(tmp_path) -> None:
    """Pruning deletes the oldest backups beyond the configured limit."""
    store = BackupStore(tmp_path)
    for backup_id, date in (
        ("backup1", "2026-08-30T23:00:00+00:00"),
        ("backup2", "2026-08-30T23:10:00+00:00"),
        ("backup3", "2026-08-30T23:20:00+00:00"),
    ):
        store.create_backup(backup_id, {"date": date}, iter([backup_id.encode()]))

    deleted = store.prune_backups(2)

    assert deleted == ["backup1"]
    assert sorted(backup["backup_id"] for backup in store.list_backups()) == [
        "backup2",
        "backup3",
    ]


def test_prune_zero_or_negative_is_unlimited(tmp_path) -> None:
    """max_backups <= 0 means "keep everything"."""
    store = BackupStore(tmp_path)
    store.create_backup("backup1", {"date": "2026-08-30T23:00:00+00:00"}, iter([b"abc"]))

    assert not store.prune_backups(0)
    assert not store.prune_backups(-1)
    assert len(store.list_backups()) == 1


def test_parse_backup_date_invalid_returns_min() -> None:
    """Invalid dates sort as the oldest possible value."""
    assert parse_backup_date("not-a-date") == parse_backup_date("0001-01-01T00:00:00")
