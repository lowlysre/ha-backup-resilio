"""Thin async client for the Resilio Sync local API."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Mapping
from typing import Any

import aiohttp

from homeassistant.helpers.aiohttp_client import async_get_clientsession

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)


class ResilioApiError(Exception):
    """Base Resilio API error."""


class ResilioConnectionError(ResilioApiError):
    """Raised when the Resilio API is unreachable."""


class ResilioAuthError(ResilioApiError):
    """Raised when the Resilio API rejects credentials."""


class ResilioFolderNotFoundError(ResilioApiError):
    """Raised when the configured folder no longer exists."""


class ResilioApiClient:
    """Async client for the Resilio Sync local API."""

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
        self._base_url = f"{scheme}://{host}:{port}/api/v2"
        self._ssl = not use_ssl or verify_ssl
        # aiohttp.BasicAuth is deprecated in favor of a plain header; built manually
        # here to avoid depending on a specific aiohttp version's replacement helper.
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        # Resilio also checks the request origin against its own address.
        self._headers = {
            "Referer": f"{self._base_url}/",
            "Authorization": f"Basic {credentials}",
        }

    async def _async_request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        not_found_error: type[ResilioApiError] | None = None,
    ) -> Any:
        """Perform a request against the Resilio API."""
        try:
            async with self._session.request(
                method,
                f"{self._base_url}{path}",
                headers=self._headers,
                json=json_body,
                timeout=REQUEST_TIMEOUT,
                ssl=self._ssl,
            ) as response:
                if response.status in (401, 403):
                    raise ResilioAuthError("Invalid Resilio API credentials")
                if response.status == 404 and not_found_error is not None:
                    raise not_found_error(f"Resilio resource not found: {path}")
                if response.status < 200 or response.status >= 300:
                    raise ResilioApiError(
                        f"Resilio API request failed with status {response.status}"
                    )
                return await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise ResilioConnectionError("Unable to connect to the Resilio API") from err

    async def async_get_os(self) -> dict[str, Any]:
        """Fetch the OS endpoint as a connectivity check."""
        response = await self._async_request("GET", "/os")
        if isinstance(response, dict):
            return response
        return {"response": response}

    async def async_get_folders(self) -> list[dict[str, Any]]:
        """Fetch all managed folders."""
        response = await self._async_request("GET", "/folders")
        if isinstance(response, list):
            return [folder for folder in response if isinstance(folder, dict)]
        if isinstance(response, dict) and isinstance(response.get("folders"), list):
            return [folder for folder in response["folders"] if isinstance(folder, dict)]
        raise ResilioApiError("Unexpected folders response from Resilio API")

    async def async_get_folder(self, folder_id: str) -> dict[str, Any]:
        """Fetch a single folder."""
        response = await self._async_request(
            "GET",
            f"/folders/{folder_id}",
            not_found_error=ResilioFolderNotFoundError,
        )
        if not isinstance(response, dict):
            raise ResilioApiError("Unexpected folder response from Resilio API")
        return response

    async def async_add_folder(self, path: str) -> dict[str, Any]:
        """Create or add a folder for Resilio to manage."""
        response = await self._async_request("POST", "/folders", json_body={"path": path})
        if not isinstance(response, dict):
            raise ResilioApiError("Unexpected folder response from Resilio API")
        return response
