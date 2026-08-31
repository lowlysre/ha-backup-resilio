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
from custom_components.resilio_backup.coordinator import ResilioDataUpdateCoordinator
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
    assert data.state == "in sync"


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
