"""Thin async client for the Resilio Sync WebUI API."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Mapping
import logging
import re
import time
from typing import Any

import aiohttp

from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)
_TOKEN_PATTERN = re.compile(r"id=['\"]token['\"][^>]*>(?P<token>[\w-]+)<")


class ResilioApiError(Exception):
    """Base Resilio API error."""


class ResilioConnectionError(ResilioApiError):
    """Raised when the Resilio API is unreachable."""


class ResilioAuthError(ResilioApiError):
    """Raised when the Resilio API rejects credentials."""


class ResilioFolderNotFoundError(ResilioApiError):
    """Raised when the configured folder no longer exists."""


def _timestamp_ms() -> int:
    """Return the current time in milliseconds, as the WebUI expects."""
    return int(time.time() * 1000)


class ResilioApiClient:
    """Async client for Resilio Sync's undocumented WebUI API.

    Resilio Sync has no REST API on the free tier: the documented ``/api/v2``
    endpoints (https://github.com/bt-sync/sync_api_sample) return HTTP 400 on
    an unlicensed install, confirmed against a live agent, since that API is
    gated behind a paid Business license
    (https://help.resilio.com/hc/en-us/articles/360013238759).

    This instead drives the same internal ``/gui/`` endpoint the WebUI itself
    uses: a CSRF token minted from ``/gui/token.html`` plus its session
    cookie, both attached to every ``action=`` query call. That's the
    approach taken by the reverse-engineered clients ``rslsync``
    (https://github.com/zhongkechen/python-resilio-sync-unofficial) and
    ``resilio-sync-cli`` (https://github.com/PythonNut/resilio-sync-cli),
    which remain the only working references for a free-tier install; there
    is no official documentation for this protocol.
    """

    # pylint: disable=too-many-positional-arguments
    def __init__(
        self,
        hass,
        host: str,
        port: int,
        username: str,
        password: str,
        use_ssl: bool = False,
        verify_ssl: bool = True,
    ) -> None:
        """Initialize the API client."""
        self._session = async_get_clientsession(hass)
        scheme = "https" if use_ssl else "http"
        self._base_url = f"{scheme}://{host}:{port}/gui"
        self._ssl = not use_ssl or verify_ssl
        # aiohttp.BasicAuth is deprecated in favor of a plain header; built manually
        # here to avoid depending on a specific aiohttp version's replacement helper.
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._auth_header = {"Authorization": f"Basic {credentials}"}
        self._token: str | None = None
        self._cookie: str | None = None

    async def _async_fetch_token(self) -> None:
        """Mint a fresh CSRF token and session cookie from the WebUI."""
        url = f"{self._base_url}/token.html"
        try:
            async with self._session.get(
                url,
                headers=self._auth_header,
                params={"t": _timestamp_ms()},
                timeout=REQUEST_TIMEOUT,
                ssl=self._ssl,
            ) as response:
                if response.status in (401, 403):
                    raise ResilioAuthError("Invalid Resilio API credentials")
                if response.status < 200 or response.status >= 300:
                    raise ResilioApiError(
                        f"Resilio token request failed with status {response.status}"
                    )
                body = await response.text()
                cookie = response.headers.get("Set-Cookie")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Unable to reach Resilio WebUI at %s: %s", url, err)
            raise ResilioConnectionError("Unable to connect to the Resilio API") from err

        match = _TOKEN_PATTERN.search(body)
        if not match or not cookie:
            raise ResilioApiError("Resilio WebUI did not return a valid session token")
        self._token = match.group("token")
        self._cookie = cookie.split(";", 1)[0]

    async def _async_request(
        self, action: str, *, params: Mapping[str, Any] | None = None, _retry: bool = True
    ) -> dict[str, Any]:
        """Call a ``/gui/`` WebUI action and return its decoded response.

        Every WebUI action response is a flat dict with a ``status`` field,
        where 200 means success. That's different from the licensed
        ``/api/v2`` envelope (``{"data": ..., "status": 0}``), which this
        client no longer talks to.
        """
        if self._token is None:
            await self._async_fetch_token()

        url = f"{self._base_url}/"
        query = {"token": self._token, "action": action, "t": _timestamp_ms(), **(params or {})}
        headers = {**self._auth_header, "Cookie": self._cookie}
        try:
            async with self._session.get(
                url,
                headers=headers,
                params=query,
                timeout=REQUEST_TIMEOUT,
                ssl=self._ssl,
            ) as response:
                if response.status in (401, 403):
                    raise ResilioAuthError("Invalid Resilio API credentials")
                if response.status < 200 or response.status >= 300:
                    body = await response.text()
                    _LOGGER.debug(
                        "Resilio API action %s failed with HTTP %s: %s",
                        action,
                        response.status,
                        body,
                    )
                    raise ResilioApiError(
                        f"Resilio API request failed with status {response.status}"
                    )
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Unable to reach Resilio API at %s: %s", url, err)
            raise ResilioConnectionError("Unable to connect to the Resilio API") from err

        if not isinstance(payload, dict):
            raise ResilioApiError(f"Unexpected Resilio API response for action {action}")

        status = payload.get("status")
        if status == 401 and _retry:
            # The session cookie/token can expire independently of the
            # underlying credentials; remint once before giving up.
            self._token = None
            return await self._async_request(action, params=params, _retry=False)
        if isinstance(status, int) and status not in (200, 0):
            _LOGGER.debug(
                "Resilio API action %s reported status %s: %s", action, status, payload
            )
            raise ResilioApiError(
                f"Resilio API reported failure status {status} for action {action}"
            )
        return payload

    async def async_get_os(self) -> dict[str, Any]:
        """Fetch system info as a connectivity and credentials check."""
        return await self._async_request("getsysteminfo")

    async def async_get_folders(self) -> list[dict[str, Any]]:
        """Fetch all managed folders, normalized to expose an ``id`` key."""
        payload = await self._async_request("getsyncfolders", params={"discovery": 1})
        folders = payload.get("folders")
        if not isinstance(folders, list):
            raise ResilioApiError("Unexpected folders response from Resilio API")
        return [
            {**folder, "id": folder["folderid"]}
            for folder in folders
            if isinstance(folder, dict) and "folderid" in folder
        ]

    async def async_get_folder(self, folder_id: str) -> dict[str, Any]:
        """Fetch a single folder by id."""
        for folder in await self.async_get_folders():
            if str(folder.get("id")) == str(folder_id):
                return folder
        raise ResilioFolderNotFoundError(f"Resilio folder not found: {folder_id}")

    async def async_get_share_link(
        self,
        folder_id: str,
        folder_name: str,
        *,
        permission: int = 3,
        timelimit: int = 7 * 24 * 3600,
    ) -> str:
        """Generate a peer-invite link for a folder, or "" if none was produced.

        Captured live against an unlicensed ``resilio/sync`` container
        (see ``tools/resilio_capture``, lowlysre/ha-backup-resilio#5):
        ``permissions`` uses Resilio's own 2 (read-only)/3 (read-write)/
        4 (owner)/5 (encrypted)/6 (archive) scale, not the 1/2/4 scale some
        reverse-engineered clients assume. ``askapproval=1`` also isn't
        usable on a free-tier agent -- it 500s internally
        (``Failed to create a link of type APPROVE_NEW, because MD is not
        set``), so links are generated unmoderated instead. A successful
        call still returns an empty ``value`` if Resilio silently declines
        to mint one, so callers should treat "" as "no link available"
        rather than an error.
        """
        payload = await self._async_request(
            "getsynclink",
            params={
                "name": folder_name,
                "folderid": folder_id,
                "permissions": permission,
                "timelimit": timelimit,
                "type": "copy",
                "linktype": "https",
                "clicklimit": 0,
                "askapproval": 0,
            },
        )
        link = payload.get("value")
        return link if isinstance(link, str) else ""

    async def async_add_folder(self, path: str) -> dict[str, Any]:
        """Create a folder for Resilio to manage and return its normalized info.

        ``addsyncfolder`` doesn't reliably echo back the created folder's id,
        so the folder list is re-fetched and matched by path instead of
        trusting the add response's shape.
        """
        await self._async_request(
            "addsyncfolder",
            params={
                "path": path,
                "secret": "",
                "selectivesync": "false",
                "encrypted": "false",
            },
        )
        for folder in await self.async_get_folders():
            if folder.get("path") == path:
                return folder
        raise ResilioApiError(f"Resilio did not report the folder just added: {path}")
