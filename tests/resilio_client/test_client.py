"""Tests for the HA-agnostic Resilio API client."""

from __future__ import annotations

import asyncio

import aiohttp
import pytest

from custom_components.resilio_backup.resilio_client.client import (
    ResilioApiError,
    ResilioAuthError,
    ResilioClient,
    ResilioConnectionError,
    ResilioFolderNotFoundError,
)
from tests.resilio_client.fakes import FakeExceptionResponse, FakeResponse, FakeSession

MOCK_FOLDER = {
    "folderid": "folder123",
    "id": "folder123",
    "path": "/mnt/sync/folders/backups",
    "name": "Home Assistant Backups",
    "size": 2048,
    "files": 16,
    "peers": 3,
    "paused": False,
    "error": 0,
    "errors": [],
    "down_status": 100,
    "up_status": 100,
}

MOCK_OS = {"os": "windows", "version": "3.0"}
MOCK_TOKEN = "TESTTOKEN123"
MOCK_TOKEN_HTML = f"<html><div id='token' style='display:none;'>{MOCK_TOKEN}</div></html>"
MOCK_TOKEN_HEADERS = {"Set-Cookie": "SNSID=deadbeef; Path=/; HttpOnly"}


def webui_action(data: dict, *, status: int = 200) -> dict:
    """Wrap payload data the way the real Resilio Sync WebUI action API does."""
    return {**data, "status": status}


def token_response(*, status: int = 200) -> FakeResponse:
    """Build the fake response for a ``token.html`` request."""
    return FakeResponse(status=status, text=MOCK_TOKEN_HTML, headers=MOCK_TOKEN_HEADERS)


def build_client(responses: list) -> tuple[ResilioClient, FakeSession]:
    """Build a client wired to a fake session with queued responses."""
    session = FakeSession(responses)
    client = ResilioClient(
        session, "resilio.local", 8888, "admin", "secret", use_ssl=False, verify_ssl=True
    )
    return client, session


async def test_async_get_os_success() -> None:
    """The OS check hits the getsysteminfo WebUI action, minting a token first."""
    client, _session = build_client([token_response(), FakeResponse(json=webui_action(MOCK_OS))])
    assert await client.async_get_os() == {**MOCK_OS, "status": 200}


async def test_async_get_os_reuses_token() -> None:
    """A minted token is reused across calls instead of re-fetched every time."""
    client, session = build_client(
        [
            token_response(),
            FakeResponse(json=webui_action(MOCK_OS)),
            FakeResponse(json=webui_action(MOCK_OS)),
        ]
    )
    await client.async_get_os()
    await client.async_get_os()
    token_calls = [call for call in session.calls if "token.html" in call[0]]
    assert len(token_calls) == 1


async def test_async_fetch_token_invalid_auth() -> None:
    """401/403 while minting a token maps to an auth error."""
    client, _session = build_client([token_response(status=401)])
    with pytest.raises(ResilioAuthError):
        await client.async_get_os()


async def test_async_fetch_token_forbidden() -> None:
    """403 while minting a token maps to an auth error too."""
    client, _session = build_client([token_response(status=403)])
    with pytest.raises(ResilioAuthError):
        await client.async_get_os()


async def test_async_fetch_token_server_error() -> None:
    """Unexpected status codes while minting a token raise API errors."""
    client, _session = build_client([token_response(status=500)])
    with pytest.raises(ResilioApiError):
        await client.async_get_os()


async def test_async_fetch_token_connection_error() -> None:
    """Client errors while minting a token map to connection errors."""
    client, _session = build_client([FakeExceptionResponse(aiohttp.ClientError("boom"))])
    with pytest.raises(ResilioConnectionError):
        await client.async_get_os()


async def test_async_fetch_token_timeout() -> None:
    """Timeouts while minting a token map to connection errors."""
    client, _session = build_client([FakeExceptionResponse(asyncio.TimeoutError())])
    with pytest.raises(ResilioConnectionError):
        await client.async_get_os()


async def test_async_fetch_token_missing_token() -> None:
    """A response without a recognizable token div is an API error."""
    client, _session = build_client(
        [FakeResponse(text="<html>no token here</html>", headers={"Set-Cookie": "x=1"})]
    )
    with pytest.raises(ResilioApiError):
        await client.async_get_os()


async def test_async_fetch_token_missing_cookie() -> None:
    """A response without a session cookie is an API error."""
    client, _session = build_client(
        [FakeResponse(text="<html><div id='token'>abc</div></html>")]
    )
    with pytest.raises(ResilioApiError):
        await client.async_get_os()


async def test_async_get_os_invalid_auth() -> None:
    """401/403 on the action call maps to an auth error."""
    client, _session = build_client([token_response(), FakeResponse(status=401)])
    with pytest.raises(ResilioAuthError):
        await client.async_get_os()


async def test_async_get_os_connection_error() -> None:
    """Client errors on the action call map to connection errors."""
    client, _session = build_client(
        [token_response(), FakeExceptionResponse(aiohttp.ClientError("boom"))]
    )
    with pytest.raises(ResilioConnectionError):
        await client.async_get_os()


async def test_async_get_os_timeout() -> None:
    """Timeouts on the action call map to connection errors."""
    client, _session = build_client(
        [token_response(), FakeExceptionResponse(asyncio.TimeoutError())]
    )
    with pytest.raises(ResilioConnectionError):
        await client.async_get_os()


async def test_async_get_os_logical_failure_status() -> None:
    """A non-200/0 action status is a failure even on HTTP 200."""
    client, _session = build_client([token_response(), FakeResponse(json=webui_action({}, status=1))])
    with pytest.raises(ResilioApiError):
        await client.async_get_os()


async def test_async_get_os_non_dict_response() -> None:
    """A non-object action response is an API error."""
    client, _session = build_client([token_response(), FakeResponse(json=["oops"])])
    with pytest.raises(ResilioApiError):
        await client.async_get_os()


async def test_async_request_retries_once_on_expired_token() -> None:
    """A stale session token/cookie is re-minted once and the request retried."""
    client, _session = build_client(
        [
            token_response(),
            FakeResponse(json={"status": 401}),
            token_response(),
            FakeResponse(json=webui_action({"folders": [MOCK_FOLDER]})),
        ]
    )
    assert await client.async_get_folders() == [MOCK_FOLDER]


async def test_async_request_gives_up_after_one_retry() -> None:
    """A second consecutive 401 status is surfaced, not retried forever."""
    client, _session = build_client(
        [
            token_response(),
            FakeResponse(json={"status": 401}),
            token_response(),
            FakeResponse(json={"status": 401}),
        ]
    )
    with pytest.raises(ResilioApiError):
        await client.async_get_folders()


async def test_async_get_folders_success() -> None:
    """Folders normalize ``folderid`` into an ``id`` key."""
    client, _session = build_client(
        [token_response(), FakeResponse(json=webui_action({"folders": [MOCK_FOLDER]}))]
    )
    assert await client.async_get_folders() == [MOCK_FOLDER]


async def test_async_get_folders_malformed_response() -> None:
    """A response missing the ``folders`` list raises an API error."""
    client, _session = build_client(
        [token_response(), FakeResponse(json=webui_action({"items": []}))]
    )
    with pytest.raises(ResilioApiError):
        await client.async_get_folders()


async def test_async_get_folders_skips_entries_without_folderid() -> None:
    """Entries missing a ``folderid`` are dropped rather than crashing."""
    client, _session = build_client(
        [
            token_response(),
            FakeResponse(
                json=webui_action({"folders": [MOCK_FOLDER, {"name": "no id"}]})
            ),
        ]
    )
    assert await client.async_get_folders() == [MOCK_FOLDER]


async def test_async_get_folder_success() -> None:
    """A folder can be found by id from the folder list."""
    client, _session = build_client(
        [token_response(), FakeResponse(json=webui_action({"folders": [MOCK_FOLDER]}))]
    )
    assert await client.async_get_folder("folder123") == MOCK_FOLDER


async def test_async_get_folder_skips_non_matching_entries() -> None:
    """A match past the first list entry is still found."""
    other_folder = {**MOCK_FOLDER, "folderid": "other", "id": "other", "path": "/mnt/other"}
    client, _session = build_client(
        [
            token_response(),
            FakeResponse(json=webui_action({"folders": [other_folder, MOCK_FOLDER]})),
        ]
    )
    assert await client.async_get_folder("folder123") == MOCK_FOLDER


async def test_async_get_folder_not_found() -> None:
    """A folder id absent from the folder list raises the not-found error."""
    client, _session = build_client(
        [token_response(), FakeResponse(json=webui_action({"folders": []}))]
    )
    with pytest.raises(ResilioFolderNotFoundError):
        await client.async_get_folder("folder123")


async def test_async_add_folder_success() -> None:
    """A newly added folder is looked up by path from the refreshed folder list."""
    other_folder = {**MOCK_FOLDER, "folderid": "other", "id": "other", "path": "/mnt/other"}
    client, _session = build_client(
        [
            token_response(),
            FakeResponse(json=webui_action({})),
            FakeResponse(json=webui_action({"folders": [other_folder, MOCK_FOLDER]})),
        ]
    )
    assert await client.async_add_folder(MOCK_FOLDER["path"]) == MOCK_FOLDER


async def test_async_add_folder_not_reported_back() -> None:
    """If the added folder isn't in the refreshed list, that's an API error."""
    client, _session = build_client(
        [
            token_response(),
            FakeResponse(json=webui_action({})),
            FakeResponse(json=webui_action({"folders": []})),
        ]
    )
    with pytest.raises(ResilioApiError):
        await client.async_add_folder("/mnt/sync/folders/new")


async def test_async_add_folder_server_error() -> None:
    """Unexpected status codes on the add call raise API errors."""
    client, _session = build_client([token_response(), FakeResponse(status=500)])
    with pytest.raises(ResilioApiError):
        await client.async_add_folder("/mnt/sync/folders/backups")


async def test_async_get_share_link_success() -> None:
    """A successful getsynclink call returns its ``value`` link as-is."""
    link = "https://link.resilio.com/#f=probe&sz=0&t=1&s=SECRET&i=IDENT&e=1788449679&v=2.8&a=3"
    client, _session = build_client(
        [token_response(), FakeResponse(json=webui_action({"value": link}))]
    )
    assert await client.async_get_share_link("folder123", "probe") == link


async def test_async_get_share_link_empty_value() -> None:
    """Resilio can 200 an empty link (confirmed live: askapproval=1 does this on
    an unlicensed agent); that's treated as "no link available", not an error.
    """
    client, _session = build_client(
        [token_response(), FakeResponse(json=webui_action({"value": ""}))]
    )
    assert await client.async_get_share_link("folder123", "probe") == ""


async def test_async_get_share_link_missing_value() -> None:
    """A response with no ``value`` key at all is treated the same as an empty one."""
    client, _session = build_client([token_response(), FakeResponse(json=webui_action({}))])
    assert await client.async_get_share_link("folder123", "probe") == ""


async def test_async_get_share_link_server_error() -> None:
    """Unexpected status codes on the link call raise API errors."""
    client, _session = build_client([token_response(), FakeResponse(status=500)])
    with pytest.raises(ResilioApiError):
        await client.async_get_share_link("folder123", "probe")
