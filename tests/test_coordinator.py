"""Tests for the Resilio coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.resilio_backup.api import (
    ResilioAuthError,
    ResilioConnectionError,
    ResilioFolderNotFoundError,
)
from custom_components.resilio_backup.const import (
    EVENT_FILE_COUNT_CHANGED,
    EVENT_PEER_COUNT_CHANGED,
)
from custom_components.resilio_backup.coordinator import (
    ResilioDataUpdateCoordinator,
    _safe_int,
)
from tests.common import MOCK_FOLDER, build_mock_entry


class ExposedResilioDataUpdateCoordinator(ResilioDataUpdateCoordinator):
    """Coordinator with a public test helper."""

    async def async_test_update(self):
        """Expose the protected update method for tests."""
        return await self._async_update_data()


async def test_coordinator_success(hass) -> None:
    """The coordinator maps folder data."""
    entry = build_mock_entry(hass)
    client = AsyncMock()
    client.async_get_folder.return_value = MOCK_FOLDER
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, client)

    data = await coordinator.async_test_update()

    assert data.folder_id == "folder123"
    assert data.name == "Home Assistant Backups"
    assert data.path == "C:\\Resilio\\Backups"
    assert data.size == 2048
    assert data.files == 16
    assert data.peers == 3
    assert data.state == "in_sync"


async def test_coordinator_peers_as_list(hass) -> None:
    """A `peers` field shaped as a list of peer objects counts its entries.

    Some Resilio versions return `peers` as a list of peer dicts instead of a
    count, which used to crash `int()` in the coordinator.
    """
    entry = build_mock_entry(hass)
    client = AsyncMock()
    client.async_get_folder.return_value = {
        **MOCK_FOLDER,
        "peers": [{"name": "peer-a"}, {"name": "peer-b"}],
    }
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, client)

    data = await coordinator.async_test_update()

    assert data.peers == 2


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        ([1, 2, 3], 0, 3),
        ("4", 0, 4),
        (None, 0, 0),
        ("not-a-number", 5, 5),
    ],
)
def test_safe_int(value, default, expected) -> None:
    """`_safe_int` tolerates list, numeric-string, and unconvertible shapes."""
    assert _safe_int(value, default) == expected


@pytest.mark.parametrize(
    "exception",
    [
        ResilioConnectionError("down"),
        ResilioAuthError("bad auth"),
        ResilioFolderNotFoundError("missing"),
    ],
)
async def test_coordinator_failures_map_to_update_failed(hass, exception) -> None:
    """Expected client failures map to UpdateFailed."""
    entry = build_mock_entry(hass)
    client = AsyncMock()
    client.async_get_folder.side_effect = exception
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, client)

    with pytest.raises(UpdateFailed):
        await coordinator.async_test_update()


async def test_no_events_fire_on_first_update(hass) -> None:
    """No change events fire when there's no previous fetch to compare against."""
    entry = build_mock_entry(hass)
    client = AsyncMock()
    client.async_get_folder.return_value = MOCK_FOLDER
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, client)
    events: list = []
    hass.bus.async_listen(EVENT_PEER_COUNT_CHANGED, events.append)
    hass.bus.async_listen(EVENT_FILE_COUNT_CHANGED, events.append)

    await coordinator.async_test_update()
    await hass.async_block_till_done()

    assert not events


async def test_no_events_fire_when_counts_are_unchanged(hass) -> None:
    """No change events fire when peers and files stay the same."""
    entry = build_mock_entry(hass)
    client = AsyncMock()
    client.async_get_folder.return_value = MOCK_FOLDER
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, client)
    coordinator.data = await coordinator.async_test_update()
    events: list = []
    hass.bus.async_listen(EVENT_PEER_COUNT_CHANGED, events.append)
    hass.bus.async_listen(EVENT_FILE_COUNT_CHANGED, events.append)

    await coordinator.async_test_update()
    await hass.async_block_till_done()

    assert not events


async def test_peer_count_change_fires_event(hass) -> None:
    """A peer count change fires an event with the before/after counts."""
    entry = build_mock_entry(hass)
    client = AsyncMock()
    client.async_get_folder.return_value = MOCK_FOLDER
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, client)
    coordinator.data = await coordinator.async_test_update()
    events: list = []
    hass.bus.async_listen(EVENT_PEER_COUNT_CHANGED, events.append)
    client.async_get_folder.return_value = {**MOCK_FOLDER, "peers": 5}

    await coordinator.async_test_update()
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data == {
        "entry_id": entry.entry_id,
        "previous": 3,
        "current": 5,
    }


async def test_file_count_change_fires_event(hass) -> None:
    """A file count change fires an event with the before/after counts."""
    entry = build_mock_entry(hass)
    client = AsyncMock()
    client.async_get_folder.return_value = MOCK_FOLDER
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, client)
    coordinator.data = await coordinator.async_test_update()
    events: list = []
    hass.bus.async_listen(EVENT_FILE_COUNT_CHANGED, events.append)
    client.async_get_folder.return_value = {**MOCK_FOLDER, "files": 20}

    await coordinator.async_test_update()
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data == {
        "entry_id": entry.entry_id,
        "previous": 16,
        "current": 20,
    }
