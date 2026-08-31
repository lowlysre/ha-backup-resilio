"""Diagnostics support for Resilio Backup."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .api import ResilioApiClient
from .coordinator import ResilioConfigEntry
from .resilio_client.client import ResilioApiError

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME}

# Live WebUI probes to run at report time, cheapest/most-useful first. These
# are independent of the coordinator's cached data, so they still surface
# something useful when the coordinator itself is failing.
_HEALTH_CHECKS: dict[str, str] = {
    "version": "async_get_version",
    "app_info": "async_get_app_info",
    "performance_warnings": "async_get_performance_warnings",
    "statuses": "async_get_statuses",
}


async def _async_get_webui_health(client: ResilioApiClient) -> dict[str, Any]:
    """Run live WebUI health probes, capturing failures instead of raising.

    Each probe is independent: one action failing (e.g. an older Resilio
    version rejecting ``getperformancewarnings``) shouldn't stop the rest of
    the report from being generated.
    """
    health: dict[str, Any] = {}
    for key, method_name in _HEALTH_CHECKS.items():
        try:
            health[key] = await getattr(client, method_name)()
        except ResilioApiError as err:
            health[key] = {"error": str(err)}
    return health


async def async_get_config_entry_diagnostics(
    _hass: HomeAssistant, config_entry: ResilioConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime_data = config_entry.runtime_data
    return {
        "config_entry_data": async_redact_data(dict(config_entry.data), TO_REDACT),
        "coordinator_data": runtime_data.coordinator.data if runtime_data else None,
        "webui_health": (
            await _async_get_webui_health(runtime_data.client) if runtime_data else None
        ),
    }
