"""Tests for Resilio diagnostics."""

from __future__ import annotations

from custom_components.resilio_backup.diagnostics import async_get_config_entry_diagnostics
from tests.common import setup_integration


async def test_diagnostics_redacts_credentials(hass, aioclient_mock) -> None:
    """Diagnostics redact credentials and include coordinator data."""
    entry = await setup_integration(hass, aioclient_mock)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["config_entry_data"]["username"] == "**REDACTED**"
    assert diagnostics["config_entry_data"]["password"] == "**REDACTED**"
    assert diagnostics["coordinator_data"].folder_id == "folder123"
