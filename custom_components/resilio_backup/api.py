"""Thin Home Assistant wrapper around the HA-agnostic ``resilio_client``.

The connection/request logic itself lives in ``resilio_client.client``, with
no dependency on Home Assistant, so it can be exercised directly (or via the
``resilio-client`` CLI) against a live Resilio Sync agent without a full HA
install. This module only adds the one HA-specific piece: sourcing an
``aiohttp.ClientSession`` from HA's shared connection pool.
"""

from __future__ import annotations

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from resilio_client.client import (
    ResilioApiError,
    ResilioAuthError,
    ResilioClient,
    ResilioConnectionError,
    ResilioFolderNotFoundError,
)

__all__ = [
    "ResilioApiClient",
    "ResilioApiError",
    "ResilioAuthError",
    "ResilioConnectionError",
    "ResilioFolderNotFoundError",
]


class ResilioApiClient(ResilioClient):
    """Resilio API client that sources its aiohttp session from Home Assistant."""

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
        """Initialize the API client using HA's shared aiohttp session."""
        super().__init__(
            async_get_clientsession(hass), host, port, username, password, use_ssl, verify_ssl
        )
