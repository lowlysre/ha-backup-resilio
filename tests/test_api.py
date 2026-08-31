"""Tests for the Resilio API client."""

from __future__ import annotations

import asyncio

import aiohttp
import pytest

from custom_components.resilio_backup.api import (
    ResilioApiClient,
    ResilioApiError,
    ResilioAuthError,
    ResilioConnectionError,
    ResilioFolderNotFoundError,
)
from tests.common import MOCK_FOLDER, MOCK_OS, MOCK_USER_INPUT, envelope


@pytest.fixture(name="resilio_client")
def fixture_resilio_client(hass):
    """Build an API client for tests."""
    return ResilioApiClient(hass, **MOCK_USER_INPUT)


async def test_async_get_os_success(aioclient_mock, resilio_client) -> None:
    """The OS endpoint unwraps the real Resilio response envelope."""
    aioclient_mock.get(
        "http://resilio.local:8888/api/v2/os", json=envelope(MOCK_OS, path="/api/v2/os")
    )
    assert await resilio_client.async_get_os() == MOCK_OS


async def test_async_get_os_invalid_auth(aioclient_mock, resilio_client) -> None:
    """401 and 403 map to auth errors."""
    aioclient_mock.get("http://resilio.local:8888/api/v2/os", status=401)
    with pytest.raises(ResilioAuthError):
        await resilio_client.async_get_os()


async def test_async_get_os_forbidden(aioclient_mock, resilio_client) -> None:
    """403 maps to auth errors too."""
    aioclient_mock.get("http://resilio.local:8888/api/v2/os", status=403)
    with pytest.raises(ResilioAuthError):
        await resilio_client.async_get_os()


async def test_async_get_os_connection_error(aioclient_mock, resilio_client) -> None:
    """Client errors map to connection errors."""
    aioclient_mock.get(
        "http://resilio.local:8888/api/v2/os", exc=aiohttp.ClientError("boom")
    )
    with pytest.raises(ResilioConnectionError):
        await resilio_client.async_get_os()


async def test_async_get_os_timeout(aioclient_mock, resilio_client) -> None:
    """Timeouts map to connection errors."""
    aioclient_mock.get(
        "http://resilio.local:8888/api/v2/os", exc=asyncio.TimeoutError()
    )
    with pytest.raises(ResilioConnectionError):
        await resilio_client.async_get_os()


async def test_async_get_os_logical_failure_status(aioclient_mock, resilio_client) -> None:
    """A non-zero envelope status is a failure even on HTTP 200."""
    aioclient_mock.get(
        "http://resilio.local:8888/api/v2/os",
        json=envelope(None, path="/api/v2/os", status=1),
    )
    with pytest.raises(ResilioApiError):
        await resilio_client.async_get_os()


async def test_async_get_os_wraps_non_dict(aioclient_mock, resilio_client) -> None:
    """Non-dict OS responses are wrapped."""
    aioclient_mock.get(
        "http://resilio.local:8888/api/v2/os",
        json=envelope(["ok"], path="/api/v2/os"),
    )
    assert await resilio_client.async_get_os() == {"response": ["ok"]}


async def test_async_get_os_missing_envelope(aioclient_mock, resilio_client) -> None:
    """A bare (un-enveloped) dict response is still accepted defensively."""
    aioclient_mock.get("http://resilio.local:8888/api/v2/os", json=MOCK_OS)
    assert await resilio_client.async_get_os() == MOCK_OS


async def test_async_get_folders_success_from_dict(
    aioclient_mock, resilio_client
) -> None:
    """Folder responses normalize the real ``{"folders": [...]}`` envelope data."""
    aioclient_mock.get(
        "http://resilio.local:8888/api/v2/folders",
        json=envelope({"folders": [MOCK_FOLDER]}, path="/api/v2/folders"),
    )
    assert await resilio_client.async_get_folders() == [MOCK_FOLDER]


async def test_async_get_folders_success_from_list(
    aioclient_mock, resilio_client
) -> None:
    """Folder responses also normalize a bare list payload defensively."""
    aioclient_mock.get(
        "http://resilio.local:8888/api/v2/folders",
        json=envelope([MOCK_FOLDER], path="/api/v2/folders"),
    )
    assert await resilio_client.async_get_folders() == [MOCK_FOLDER]


async def test_async_get_folders_malformed_response(
    aioclient_mock, resilio_client
) -> None:
    """Unexpected folder payloads raise API errors."""
    aioclient_mock.get(
        "http://resilio.local:8888/api/v2/folders",
        json=envelope({"items": []}, path="/api/v2/folders"),
    )
    with pytest.raises(ResilioApiError):
        await resilio_client.async_get_folders()


async def test_async_get_folder_success(aioclient_mock, resilio_client) -> None:
    """A folder can be fetched and unwrapped from the envelope."""
    aioclient_mock.get(
        "http://resilio.local:8888/api/v2/folders/folder123",
        json=envelope(MOCK_FOLDER, path="/api/v2/folders/folder123"),
    )
    assert await resilio_client.async_get_folder("folder123") == MOCK_FOLDER


async def test_async_get_folder_not_found(aioclient_mock, resilio_client) -> None:
    """404 maps to the folder not found error."""
    aioclient_mock.get("http://resilio.local:8888/api/v2/folders/folder123", status=404)
    with pytest.raises(ResilioFolderNotFoundError):
        await resilio_client.async_get_folder("folder123")


async def test_async_get_folder_malformed_response(
    aioclient_mock, resilio_client
) -> None:
    """Folder detail must be an object."""
    aioclient_mock.get(
        "http://resilio.local:8888/api/v2/folders/folder123",
        json=envelope([], path="/api/v2/folders/folder123"),
    )
    with pytest.raises(ResilioApiError):
        await resilio_client.async_get_folder("folder123")


async def test_async_add_folder_success(aioclient_mock, resilio_client) -> None:
    """Folders can be created and unwrapped from the envelope."""
    aioclient_mock.post(
        "http://resilio.local:8888/api/v2/folders",
        json=envelope(MOCK_FOLDER, method="POST", path="/api/v2/folders"),
    )
    assert await resilio_client.async_add_folder("C:\\Resilio\\Backups") == MOCK_FOLDER


async def test_async_add_folder_malformed_response(
    aioclient_mock, resilio_client
) -> None:
    """Folder creation must return an object."""
    aioclient_mock.post(
        "http://resilio.local:8888/api/v2/folders",
        json=envelope(["bad"], method="POST", path="/api/v2/folders"),
    )
    with pytest.raises(ResilioApiError):
        await resilio_client.async_add_folder("C:\\Resilio\\Backups")


async def test_async_add_folder_server_error(aioclient_mock, resilio_client) -> None:
    """Unexpected status codes raise API errors."""
    aioclient_mock.post("http://resilio.local:8888/api/v2/folders", status=500)
    with pytest.raises(ResilioApiError):
        await resilio_client.async_add_folder("C:\\Resilio\\Backups")
