"""Tests for Resilio Backup logbook event descriptions."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.logbook import LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.core import Event

from custom_components.resilio_backup.const import (
    EVENT_BACKUPS_PRUNED,
    EVENT_FILE_COUNT_CHANGED,
    EVENT_PEER_COUNT_CHANGED,
)
from custom_components.resilio_backup.logbook import async_describe_events
from tests.common import build_mock_entry


def _describe(hass, event_type: str, data: dict):
    """Call the registered describe function for one event type."""
    described: dict[str, Callable] = {}

    def _capture(_domain, described_event_type, describe_fn):
        described[described_event_type] = describe_fn

    async_describe_events(hass, _capture)
    return described[event_type](Event(event_type, data))


async def test_describe_peer_connected(hass) -> None:
    """A peer count increase reads as a connect."""
    entry = build_mock_entry(hass)
    entry.add_to_hass(hass)

    result = _describe(
        hass,
        EVENT_PEER_COUNT_CHANGED,
        {"entry_id": entry.entry_id, "previous": 2, "current": 3},
    )

    assert result[LOGBOOK_ENTRY_NAME] == entry.title
    assert "connected" in result[LOGBOOK_ENTRY_MESSAGE]
    assert "2" in result[LOGBOOK_ENTRY_MESSAGE]
    assert "3" in result[LOGBOOK_ENTRY_MESSAGE]


async def test_describe_peer_disconnected(hass) -> None:
    """A peer count decrease reads as a disconnect."""
    entry = build_mock_entry(hass)
    entry.add_to_hass(hass)

    result = _describe(
        hass,
        EVENT_PEER_COUNT_CHANGED,
        {"entry_id": entry.entry_id, "previous": 3, "current": 2},
    )

    assert "disconnected" in result[LOGBOOK_ENTRY_MESSAGE]


async def test_describe_peer_change_falls_back_when_entry_is_gone(hass) -> None:
    """A missing config entry still produces a readable name."""
    result = _describe(
        hass,
        EVENT_PEER_COUNT_CHANGED,
        {"entry_id": "missing", "previous": 1, "current": 2},
    )

    assert result[LOGBOOK_ENTRY_NAME] == "Resilio Backup"


async def test_describe_file_count_changed(hass) -> None:
    """A file count change reports both counts."""
    entry = build_mock_entry(hass)
    entry.add_to_hass(hass)

    result = _describe(
        hass,
        EVENT_FILE_COUNT_CHANGED,
        {"entry_id": entry.entry_id, "previous": 10, "current": 12},
    )

    assert result[LOGBOOK_ENTRY_NAME] == entry.title
    assert "10" in result[LOGBOOK_ENTRY_MESSAGE]
    assert "12" in result[LOGBOOK_ENTRY_MESSAGE]


async def test_describe_backups_pruned_singular(hass) -> None:
    """Pruning a single backup uses singular phrasing."""
    entry = build_mock_entry(hass)
    entry.add_to_hass(hass)

    result = _describe(
        hass, EVENT_BACKUPS_PRUNED, {"entry_id": entry.entry_id, "deleted": 1}
    )

    assert result[LOGBOOK_ENTRY_MESSAGE] == "pruned 1 old backup"


async def test_describe_backups_pruned_plural(hass) -> None:
    """Pruning multiple backups uses plural phrasing."""
    entry = build_mock_entry(hass)
    entry.add_to_hass(hass)

    result = _describe(
        hass, EVENT_BACKUPS_PRUNED, {"entry_id": entry.entry_id, "deleted": 3}
    )

    assert result[LOGBOOK_ENTRY_MESSAGE] == "pruned 3 old backups"
