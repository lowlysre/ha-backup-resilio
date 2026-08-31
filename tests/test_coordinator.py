"""Tests for the Resilio coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from custom_components.resilio_backup.api import (
    ResilioApiError,
    ResilioAuthError,
    ResilioConnectionError,
    ResilioFolderNotFoundError,
)
from custom_components.resilio_backup.const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_FILE_COUNT_CHANGED,
    EVENT_PEER_COUNT_CHANGED,
    ISSUE_FOLDER_NOT_FOUND,
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
    assert data.peers_total == 3
    assert data.state == "in_sync"
    assert data.last_success <= dt_util.utcnow()


def test_coordinator_uses_default_scan_interval(hass) -> None:
    """The coordinator polls at the default interval when unset."""
    entry = build_mock_entry(hass)
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, AsyncMock())

    assert coordinator.update_interval.total_seconds() == DEFAULT_SCAN_INTERVAL


def test_coordinator_uses_configured_scan_interval(hass) -> None:
    """The coordinator honors a custom polling interval option."""
    entry = build_mock_entry(hass, options={CONF_SCAN_INTERVAL: 300})
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, AsyncMock())

    assert coordinator.update_interval.total_seconds() == 300


async def test_coordinator_peers_as_list(hass) -> None:
    """A `peers` field shaped as a list of peer objects counts its entries.

    Some Resilio versions return `peers` as a list of peer dicts instead of a
    count, which used to crash `int()` in the coordinator. Without a separate
    `onlinepeerscount` field there's no way to tell connected apart from
    configured, so both collapse to the list length.
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
    assert data.peers_total == 2


async def test_coordinator_distinguishes_connected_from_total_peers(hass) -> None:
    """`onlinepeerscount` gives the connected count separately from the peer list.

    Real Resilio `/gui/` responses always carry both fields (confirmed
    against a live capture, see tools/resilio_capture/capture.py); one peer
    can be configured but offline, which `peers` (connected) alone can't
    show.
    """
    entry = build_mock_entry(hass)
    client = AsyncMock()
    client.async_get_folder.return_value = {
        **MOCK_FOLDER,
        "peers": [{"name": "peer-a"}, {"name": "peer-b"}],
        "onlinepeerscount": 1,
    }
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, client)

    data = await coordinator.async_test_update()

    assert data.peers == 1
    assert data.peers_total == 2


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
    ("overrides", "expected_state"),
    [
        ({}, "in_sync"),
        ({"error": 13}, "error"),
        ({"errors": [{"error": 13, "path": "/capture"}]}, "error"),
        ({"paused": True}, "paused"),
        ({"down_status": 40}, "syncing"),
        ({"up_status": 80}, "syncing"),
    ],
)
async def test_coordinator_derives_sync_state(hass, overrides, expected_state) -> None:
    """`state` is derived from real folder fields, not a nonexistent `state` key.

    A live capture of the `/gui/` folder object (tests/fixtures/resilio_gui/,
    see lowlysre/ha-backup-resilio#9) confirmed there's no `state` string:
    `error`/`errors`, `paused`, and `down_status`/`up_status` carry it instead.
    """
    entry = build_mock_entry(hass)
    client = AsyncMock()
    client.async_get_folder.return_value = {**MOCK_FOLDER, **overrides}
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, client)

    data = await coordinator.async_test_update()

    assert data.state == expected_state


@pytest.mark.parametrize(
    "exception",
    [
        ResilioConnectionError("down"),
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


async def test_coordinator_auth_failure_triggers_reauth(hass) -> None:
    """An auth failure raises ConfigEntryAuthFailed to trigger the reauth flow."""
    entry = build_mock_entry(hass)
    client = AsyncMock()
    client.async_get_folder.side_effect = ResilioAuthError("bad auth")
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator.async_test_update()


async def test_coordinator_folder_not_found_raises_repair_issue(hass) -> None:
    """A missing folder raises a repair issue pointing at reconfigure/recreate."""
    entry = build_mock_entry(hass)
    client = AsyncMock()
    client.async_get_folder.side_effect = ResilioFolderNotFoundError("missing")
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, client)

    with pytest.raises(UpdateFailed):
        await coordinator.async_test_update()

    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"{ISSUE_FOLDER_NOT_FOUND}_{entry.entry_id}"
    )
    assert issue is not None
    assert issue.translation_key == ISSUE_FOLDER_NOT_FOUND


async def test_coordinator_clears_repair_issue_on_recovery(hass) -> None:
    """A successful update after a missing folder clears the repair issue."""
    entry = build_mock_entry(hass)
    client = AsyncMock()
    client.async_get_folder.side_effect = ResilioFolderNotFoundError("missing")
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, client)
    issue_id = f"{ISSUE_FOLDER_NOT_FOUND}_{entry.entry_id}"

    with pytest.raises(UpdateFailed):
        await coordinator.async_test_update()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    client.async_get_folder.side_effect = None
    client.async_get_folder.return_value = MOCK_FOLDER
    await coordinator.async_test_update()

    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


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


async def test_coordinator_fetches_version_and_performance_warnings(hass) -> None:
    """A successful poll surfaces Resilio's own version and warning list."""
    entry = build_mock_entry(hass)
    client = AsyncMock()
    client.async_get_folder.return_value = MOCK_FOLDER
    client.async_get_version.return_value = {"value": "2.7.2.1370"}
    client.async_get_performance_warnings.return_value = {"warnings": ["Low disk space"]}
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, client)

    data = await coordinator.async_test_update()

    assert data.resilio_version == "2.7.2.1370"
    assert data.performance_warnings == ("Low disk space",)


async def test_coordinator_falls_back_to_previous_version_on_probe_failure(hass) -> None:
    """A failed version probe keeps the last known value instead of blanking it.

    Prevents a diagnostic sensor from flapping to unknown on a single
    transient failure of an otherwise-healthy poll.
    """
    entry = build_mock_entry(hass)
    client = AsyncMock()
    client.async_get_folder.return_value = MOCK_FOLDER
    client.async_get_version.return_value = {"value": "2.7.2.1370"}
    client.async_get_performance_warnings.return_value = {"warnings": []}
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, client)
    coordinator.data = await coordinator.async_test_update()

    client.async_get_version.side_effect = ResilioApiError("unsupported action")
    data = await coordinator.async_test_update()

    assert data.resilio_version == "2.7.2.1370"


async def test_coordinator_falls_back_to_previous_warnings_on_probe_failure(hass) -> None:
    """A failed performance-warnings probe keeps the last known warnings."""
    entry = build_mock_entry(hass)
    client = AsyncMock()
    client.async_get_folder.return_value = MOCK_FOLDER
    client.async_get_version.return_value = {"value": "2.7.2.1370"}
    client.async_get_performance_warnings.return_value = {"warnings": ["Low disk space"]}
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, client)
    coordinator.data = await coordinator.async_test_update()

    client.async_get_performance_warnings.side_effect = ResilioApiError("unsupported action")
    data = await coordinator.async_test_update()

    assert data.performance_warnings == ("Low disk space",)


async def test_coordinator_version_and_warnings_default_none_on_first_failure(hass) -> None:
    """With no previous data, a failed probe has nothing to fall back to."""
    entry = build_mock_entry(hass)
    client = AsyncMock()
    client.async_get_folder.return_value = MOCK_FOLDER
    client.async_get_version.side_effect = ResilioApiError("unsupported action")
    client.async_get_performance_warnings.side_effect = ResilioApiError("unsupported action")
    coordinator = ExposedResilioDataUpdateCoordinator(hass, entry, client)

    data = await coordinator.async_test_update()

    assert data.resilio_version is None
    assert data.performance_warnings == ()
