"""Tests for the Home Assistant wrapper around resilio_client.

Request/response behavior for the Resilio WebUI API itself (token minting,
retries, folder/link parsing, error mapping) is covered directly against the
HA-agnostic core client in ``tests/resilio_client/test_client.py``. These
tests only cover the one thing this wrapper adds: sourcing its aiohttp
session from Home Assistant.
"""

from __future__ import annotations

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.resilio_backup.api import ResilioApiClient
from resilio_client.client import ResilioClient
from tests.common import MOCK_USER_INPUT


async def test_resilio_api_client_is_a_resilio_client(hass) -> None:
    """ResilioApiClient is usable everywhere a core ResilioClient is."""
    client = ResilioApiClient(hass, **MOCK_USER_INPUT)
    assert isinstance(client, ResilioClient)


async def test_resilio_api_client_uses_hass_session(hass) -> None:
    """The wrapper sources its aiohttp session from Home Assistant's shared pool."""
    # pylint: disable=protected-access
    client = ResilioApiClient(hass, **MOCK_USER_INPUT)
    assert client._session is async_get_clientsession(hass)
