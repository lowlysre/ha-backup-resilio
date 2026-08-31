"""Tests for Resilio diagnostics."""

from __future__ import annotations

from custom_components.resilio_backup.diagnostics import async_get_config_entry_diagnostics
from tests.common import webui_action, setup_integration


BASE_URL = "http://resilio.local:8888/gui"


def _mock_health_actions(aioclient_mock, *, skip: set[str] | None = None, **overrides) -> None:
    """Register the live WebUI health-probe actions diagnostics calls."""
    actions = {
        "version": {"value": "2.7.2.1370"},
        "getappinfo": {"platform": "windows"},
        "getperformancewarnings": {"warnings": []},
        "getstatuses": {"status_list": []},
        **overrides,
    }
    for action, payload in actions.items():
        if skip and action in skip:
            continue
        aioclient_mock.get(
            f"{BASE_URL}/",
            params={"action": action},
            json=webui_action(payload),
        )


async def test_diagnostics_redacts_credentials(hass, aioclient_mock) -> None:
    """Diagnostics redact credentials and include coordinator data."""
    entry = await setup_integration(hass, aioclient_mock)
    _mock_health_actions(aioclient_mock)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["config_entry_data"]["username"] == "**REDACTED**"
    assert diagnostics["config_entry_data"]["password"] == "**REDACTED**"
    assert diagnostics["coordinator_data"].folder_id == "folder123"


async def test_diagnostics_includes_webui_health(hass, aioclient_mock) -> None:
    """Diagnostics include live WebUI health-probe results."""
    entry = await setup_integration(hass, aioclient_mock)
    _mock_health_actions(aioclient_mock)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    health = diagnostics["webui_health"]
    assert health["version"]["value"] == "2.7.2.1370"
    assert health["app_info"]["platform"] == "windows"
    assert health["performance_warnings"]["warnings"] == []
    assert health["statuses"]["status_list"] == []


async def test_diagnostics_webui_health_captures_action_failure(hass, aioclient_mock) -> None:
    """A single failing health probe reports its error without failing the rest."""
    entry = await setup_integration(hass, aioclient_mock)
    _mock_health_actions(aioclient_mock, skip={"getperformancewarnings"})
    aioclient_mock.get(
        f"{BASE_URL}/",
        params={"action": "getperformancewarnings"},
        json=webui_action({}, status=500),
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    health = diagnostics["webui_health"]
    assert "error" in health["performance_warnings"]
    assert health["version"]["value"] == "2.7.2.1370"
