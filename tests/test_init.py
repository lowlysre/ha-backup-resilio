"""Tests for integration setup and teardown."""

from __future__ import annotations

from unittest.mock import patch

import aiohttp

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED

from custom_components.resilio_backup.const import DATA_PENDING_LOCATIONS_CHECK
from tests.common import MOCK_FOLDER, build_mock_entry, mock_token_endpoint, setup_integration


async def test_setup_entry_success(hass, aioclient_mock) -> None:
    """The config entry sets up successfully."""
    entry = await setup_integration(hass, aioclient_mock)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.coordinator.data.folder_id == MOCK_FOLDER["id"]


async def test_setup_entry_not_ready_on_refresh_failure(hass, aioclient_mock) -> None:
    """Coordinator refresh failures leave the entry in retry state."""
    entry = build_mock_entry(hass)
    entry.add_to_hass(hass)
    base_url = "http://resilio.local:8888/gui"
    mock_token_endpoint(aioclient_mock, base_url)
    aioclient_mock.get(
        f"{base_url}/",
        params={"action": "getsyncfolders"},
        exc=aiohttp.ClientError("down"),
    )

    assert await hass.config_entries.async_setup(entry.entry_id) is False
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_entry_success(hass, aioclient_mock) -> None:
    """The config entry unloads cleanly."""
    entry = await setup_integration(hass, aioclient_mock)

    assert await hass.config_entries.async_unload(entry.entry_id) is True
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_options_update_schedules_reload(hass) -> None:
    """Options updates schedule a reload."""
    entry = build_mock_entry(hass)
    entry.add_to_hass(hass)

    with patch.object(hass.config_entries, "async_schedule_reload") as schedule_reload:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        await hass.config_entries.options.async_configure(
            result["flow_id"], {"scan_interval": 120}
        )
        await hass.async_block_till_done()

    schedule_reload.assert_called_once_with(entry.entry_id)


async def test_pending_locations_check_notifies_after_restart(hass, aioclient_mock) -> None:
    """A pending flag left by a real reconfigure fires a reminder on next restart.

    Only ``EVENT_HOMEASSISTANT_STARTED`` (a genuine full restart) should
    trigger this, never a live config entry reload (lowlysre/ha-backup-resilio#30).
    """
    entry = await setup_integration(hass, aioclient_mock)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, DATA_PENDING_LOCATIONS_CHECK: True}
    )

    with patch(
        "custom_components.resilio_backup.persistent_notification.async_create"
    ) as notify:
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
        await hass.async_block_till_done()

    notify.assert_called_once()
    assert notify.call_args.kwargs["title"] == "Resilio Backup: check backup locations"
    assert DATA_PENDING_LOCATIONS_CHECK not in entry.data


async def test_pending_locations_check_noop_without_flag(hass, aioclient_mock) -> None:
    """No reminder fires on restart when no reconfigure ever set the flag."""
    await setup_integration(hass, aioclient_mock)

    with patch(
        "custom_components.resilio_backup.persistent_notification.async_create"
    ) as notify:
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
        await hass.async_block_till_done()

    notify.assert_not_called()
