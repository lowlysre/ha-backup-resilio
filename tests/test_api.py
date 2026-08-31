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
from tests.common import (
    MOCK_FOLDER,
    MOCK_OS,
    MOCK_USER_INPUT,
    mock_token_endpoint,
    webui_action,
)

BASE_URL = "http://resilio.local:8888/gui"


@pytest.fixture(name="resilio_client")
def fixture_resilio_client(hass):
    """Build an API client for tests."""
    return ResilioApiClient(hass, **MOCK_USER_INPUT)


async def test_async_get_os_success(aioclient_mock, resilio_client) -> None:
    """The OS check hits the getsysteminfo WebUI action, minting a token first."""
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(
        f"{BASE_URL}/", params={"action": "getsysteminfo"}, json=webui_action(MOCK_OS)
    )
    assert await resilio_client.async_get_os() == {**MOCK_OS, "status": 200}


async def test_async_get_os_reuses_token(aioclient_mock, resilio_client) -> None:
    """A minted token is reused across calls instead of re-fetched every time."""
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(
        f"{BASE_URL}/", params={"action": "getsysteminfo"}, json=webui_action(MOCK_OS)
    )
    await resilio_client.async_get_os()
    await resilio_client.async_get_os()
    token_calls = [call for call in aioclient_mock.mock_calls if "token.html" in str(call[1])]
    assert len(token_calls) == 1


async def test_async_fetch_token_invalid_auth(aioclient_mock, resilio_client) -> None:
    """401/403 while minting a token maps to an auth error."""
    aioclient_mock.get(f"{BASE_URL}/token.html", status=401)
    with pytest.raises(ResilioAuthError):
        await resilio_client.async_get_os()


async def test_async_fetch_token_forbidden(aioclient_mock, resilio_client) -> None:
    """403 while minting a token maps to an auth error too."""
    aioclient_mock.get(f"{BASE_URL}/token.html", status=403)
    with pytest.raises(ResilioAuthError):
        await resilio_client.async_get_os()


async def test_async_fetch_token_server_error(aioclient_mock, resilio_client) -> None:
    """Unexpected status codes while minting a token raise API errors."""
    aioclient_mock.get(f"{BASE_URL}/token.html", status=500)
    with pytest.raises(ResilioApiError):
        await resilio_client.async_get_os()


async def test_async_fetch_token_connection_error(aioclient_mock, resilio_client) -> None:
    """Client errors while minting a token map to connection errors."""
    aioclient_mock.get(f"{BASE_URL}/token.html", exc=aiohttp.ClientError("boom"))
    with pytest.raises(ResilioConnectionError):
        await resilio_client.async_get_os()


async def test_async_fetch_token_timeout(aioclient_mock, resilio_client) -> None:
    """Timeouts while minting a token map to connection errors."""
    aioclient_mock.get(f"{BASE_URL}/token.html", exc=asyncio.TimeoutError())
    with pytest.raises(ResilioConnectionError):
        await resilio_client.async_get_os()


async def test_async_fetch_token_missing_token(aioclient_mock, resilio_client) -> None:
    """A response without a recognizable token div is an API error."""
    aioclient_mock.get(
        f"{BASE_URL}/token.html", text="<html>no token here</html>", headers={"Set-Cookie": "x=1"}
    )
    with pytest.raises(ResilioApiError):
        await resilio_client.async_get_os()


async def test_async_fetch_token_missing_cookie(aioclient_mock, resilio_client) -> None:
    """A response without a session cookie is an API error."""
    aioclient_mock.get(
        f"{BASE_URL}/token.html",
        text="<html><div id='token'>abc</div></html>",
    )
    with pytest.raises(ResilioApiError):
        await resilio_client.async_get_os()


async def test_async_get_os_invalid_auth(aioclient_mock, resilio_client) -> None:
    """401/403 on the action call maps to an auth error."""
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(f"{BASE_URL}/", params={"action": "getsysteminfo"}, status=401)
    with pytest.raises(ResilioAuthError):
        await resilio_client.async_get_os()


async def test_async_get_os_connection_error(aioclient_mock, resilio_client) -> None:
    """Client errors on the action call map to connection errors."""
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(
        f"{BASE_URL}/", params={"action": "getsysteminfo"}, exc=aiohttp.ClientError("boom")
    )
    with pytest.raises(ResilioConnectionError):
        await resilio_client.async_get_os()


async def test_async_get_os_timeout(aioclient_mock, resilio_client) -> None:
    """Timeouts on the action call map to connection errors."""
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(
        f"{BASE_URL}/", params={"action": "getsysteminfo"}, exc=asyncio.TimeoutError()
    )
    with pytest.raises(ResilioConnectionError):
        await resilio_client.async_get_os()


async def test_async_get_os_logical_failure_status(aioclient_mock, resilio_client) -> None:
    """A non-200/0 action status is a failure even on HTTP 200."""
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(
        f"{BASE_URL}/", params={"action": "getsysteminfo"}, json=webui_action({}, status=1)
    )
    with pytest.raises(ResilioApiError):
        await resilio_client.async_get_os()


async def test_async_get_os_non_dict_response(aioclient_mock, resilio_client) -> None:
    """A non-object action response is an API error."""
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(f"{BASE_URL}/", params={"action": "getsysteminfo"}, json=["oops"])
    with pytest.raises(ResilioApiError):
        await resilio_client.async_get_os()


async def test_async_request_retries_once_on_expired_token(
    aioclient_mock, resilio_client, monkeypatch
) -> None:
    """A stale session token/cookie is re-minted once and the request retried."""
    # pylint: disable=protected-access
    tokens = iter(["fresh-token"])

    async def fake_fetch_token() -> None:
        resilio_client._token = next(tokens)
        resilio_client._cookie = "SNSID=fresh"

    monkeypatch.setattr(resilio_client, "_async_fetch_token", fake_fetch_token)
    resilio_client._token = "stale-token"
    resilio_client._cookie = "SNSID=stale"

    aioclient_mock.get(
        f"{BASE_URL}/",
        params={"action": "getsyncfolders", "token": "stale-token"},
        json={"status": 401},
    )
    aioclient_mock.get(
        f"{BASE_URL}/",
        params={"action": "getsyncfolders", "token": "fresh-token"},
        json=webui_action({"folders": [MOCK_FOLDER]}),
    )

    assert await resilio_client.async_get_folders() == [MOCK_FOLDER]


async def test_async_request_gives_up_after_one_retry(
    aioclient_mock, resilio_client, monkeypatch
) -> None:
    """A second consecutive 401 status is surfaced, not retried forever."""
    # pylint: disable=protected-access
    call_count = 0

    async def fake_fetch_token() -> None:
        nonlocal call_count
        call_count += 1
        resilio_client._token = f"token-{call_count}"
        resilio_client._cookie = "SNSID=fresh"

    monkeypatch.setattr(resilio_client, "_async_fetch_token", fake_fetch_token)
    resilio_client._token = "token-0"
    resilio_client._cookie = "SNSID=stale"

    aioclient_mock.get(f"{BASE_URL}/", json={"status": 401})

    with pytest.raises(ResilioApiError):
        await resilio_client.async_get_folders()


async def test_async_get_folders_success(aioclient_mock, resilio_client) -> None:
    """Folders normalize ``folderid`` into an ``id`` key."""
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(
        f"{BASE_URL}/",
        params={"action": "getsyncfolders"},
        json=webui_action({"folders": [MOCK_FOLDER]}),
    )
    assert await resilio_client.async_get_folders() == [MOCK_FOLDER]


async def test_async_get_folders_malformed_response(aioclient_mock, resilio_client) -> None:
    """A response missing the ``folders`` list raises an API error."""
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(
        f"{BASE_URL}/", params={"action": "getsyncfolders"}, json=webui_action({"items": []})
    )
    with pytest.raises(ResilioApiError):
        await resilio_client.async_get_folders()


async def test_async_get_folders_skips_entries_without_folderid(
    aioclient_mock, resilio_client
) -> None:
    """Entries missing a ``folderid`` are dropped rather than crashing."""
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(
        f"{BASE_URL}/",
        params={"action": "getsyncfolders"},
        json=webui_action({"folders": [MOCK_FOLDER, {"name": "no id"}]}),
    )
    assert await resilio_client.async_get_folders() == [MOCK_FOLDER]


async def test_async_get_folder_success(aioclient_mock, resilio_client) -> None:
    """A folder can be found by id from the folder list."""
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(
        f"{BASE_URL}/",
        params={"action": "getsyncfolders"},
        json=webui_action({"folders": [MOCK_FOLDER]}),
    )
    assert await resilio_client.async_get_folder("folder123") == MOCK_FOLDER


async def test_async_get_folder_skips_non_matching_entries(
    aioclient_mock, resilio_client
) -> None:
    """A match past the first list entry is still found."""
    other_folder = {**MOCK_FOLDER, "folderid": "other", "id": "other", "path": "C:\\Other"}
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(
        f"{BASE_URL}/",
        params={"action": "getsyncfolders"},
        json=webui_action({"folders": [other_folder, MOCK_FOLDER]}),
    )
    assert await resilio_client.async_get_folder("folder123") == MOCK_FOLDER


async def test_async_get_folder_not_found(aioclient_mock, resilio_client) -> None:
    """A folder id absent from the folder list raises the not-found error."""
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(
        f"{BASE_URL}/", params={"action": "getsyncfolders"}, json=webui_action({"folders": []})
    )
    with pytest.raises(ResilioFolderNotFoundError):
        await resilio_client.async_get_folder("folder123")


async def test_async_add_folder_success(aioclient_mock, resilio_client) -> None:
    """A newly added folder is looked up by path from the refreshed folder list."""
    other_folder = {**MOCK_FOLDER, "folderid": "other", "id": "other", "path": "C:\\Other"}
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(
        f"{BASE_URL}/", params={"action": "addsyncfolder"}, json=webui_action({})
    )
    aioclient_mock.get(
        f"{BASE_URL}/",
        params={"action": "getsyncfolders"},
        json=webui_action({"folders": [other_folder, MOCK_FOLDER]}),
    )
    assert await resilio_client.async_add_folder(MOCK_FOLDER["path"]) == MOCK_FOLDER


async def test_async_add_folder_not_reported_back(aioclient_mock, resilio_client) -> None:
    """If the added folder isn't in the refreshed list, that's an API error."""
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(
        f"{BASE_URL}/", params={"action": "addsyncfolder"}, json=webui_action({})
    )
    aioclient_mock.get(
        f"{BASE_URL}/", params={"action": "getsyncfolders"}, json=webui_action({"folders": []})
    )
    with pytest.raises(ResilioApiError):
        await resilio_client.async_add_folder("C:\\Resilio\\NewFolder")


async def test_async_add_folder_server_error(aioclient_mock, resilio_client) -> None:
    """Unexpected status codes on the add call raise API errors."""
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(f"{BASE_URL}/", params={"action": "addsyncfolder"}, status=500)
    with pytest.raises(ResilioApiError):
        await resilio_client.async_add_folder("C:\\Resilio\\Backups")


async def test_async_get_share_link_success(aioclient_mock, resilio_client) -> None:
    """A successful getsynclink call returns its ``value`` link as-is."""
    link = "https://link.resilio.com/#f=probe&sz=0&t=1&s=SECRET&i=IDENT&e=1788449679&v=2.8&a=3"
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(
        f"{BASE_URL}/",
        params={"action": "getsynclink"},
        json=webui_action({"value": link}),
    )
    assert await resilio_client.async_get_share_link("folder123", "probe") == link


async def test_async_get_share_link_empty_value(aioclient_mock, resilio_client) -> None:
    """Resilio can 200 an empty link (confirmed live: askapproval=1 does this on
    an unlicensed agent); that's treated as "no link available", not an error.
    """
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(
        f"{BASE_URL}/",
        params={"action": "getsynclink"},
        json=webui_action({"value": ""}),
    )
    assert await resilio_client.async_get_share_link("folder123", "probe") == ""


async def test_async_get_share_link_missing_value(aioclient_mock, resilio_client) -> None:
    """A response with no ``value`` key at all is treated the same as an empty one."""
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(
        f"{BASE_URL}/", params={"action": "getsynclink"}, json=webui_action({})
    )
    assert await resilio_client.async_get_share_link("folder123", "probe") == ""


async def test_async_get_share_link_server_error(aioclient_mock, resilio_client) -> None:
    """Unexpected status codes on the link call raise API errors."""
    mock_token_endpoint(aioclient_mock, BASE_URL)
    aioclient_mock.get(f"{BASE_URL}/", params={"action": "getsynclink"}, status=500)
    with pytest.raises(ResilioApiError):
        await resilio_client.async_get_share_link("folder123", "probe")
