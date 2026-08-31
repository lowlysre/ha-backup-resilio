"""HA-agnostic async client for the Resilio Sync WebUI API.

This package has no dependency on Home Assistant: it only needs an
``aiohttp.ClientSession``. ``custom_components/resilio_backup/api.py`` wraps
``ResilioClient`` to source that session from HA's shared connection pool;
the ``resilio_client.cli`` module drives it directly, so the same request
logic can be exercised as a standalone CLI or in CI against a live Resilio
Sync container, without a Home Assistant install.
"""

from .client import (
    ResilioApiError,
    ResilioAuthError,
    ResilioClient,
    ResilioConnectionError,
    ResilioFolderNotFoundError,
)

__all__ = [
    "ResilioApiError",
    "ResilioAuthError",
    "ResilioClient",
    "ResilioConnectionError",
    "ResilioFolderNotFoundError",
]
