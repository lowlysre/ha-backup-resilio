"""Shared test helpers for Resilio Backup."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from homeassistant.components.backup.models import AddonInfo, AgentBackup, Folder
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.resilio_backup.const import (
    CONF_BACKUP_PATH,
    CONF_FOLDER_ID,
    CONF_FOLDER_PATH,
    CONF_SCAN_INTERVAL,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

MOCK_USER_INPUT = {
    CONF_HOST: "resilio.local",
    CONF_PORT: DEFAULT_PORT,
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "secret",
    CONF_USE_SSL: False,
    CONF_VERIFY_SSL: True,
}

MOCK_FOLDER = {
    "folderid": "folder123",
    "id": "folder123",
    "path": "C:\\Resilio\\Backups",
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


def webui_action(data, *, status: int = 200) -> dict:
    """Wrap payload data the way the real Resilio Sync WebUI action API does.

    Every ``/gui/?action=...`` response is a flat dict with a ``status`` field
    (200 on success), confirmed against real reverse-engineered clients
    (https://github.com/zhongkechen/python-resilio-sync-unofficial,
    https://github.com/PythonNut/resilio-sync-cli). That's a different shape
    than the licensed ``/api/v2`` envelope this integration no longer uses.
    """
    return {**data, "status": status}


def mock_token_endpoint(aioclient_mock, base_url: str) -> None:
    """Register the ``/gui/token.html`` mock every action call depends on."""
    aioclient_mock.get(
        f"{base_url}/token.html", text=MOCK_TOKEN_HTML, headers=MOCK_TOKEN_HEADERS
    )


def build_backup_dir(hass, name: str | None = None) -> Path:
    """Build a backup directory inside the test config path."""
    return Path(hass.config.path(name or f"resilio_backups_{uuid4().hex}"))


def build_mock_entry(hass, options=None, **overrides) -> MockConfigEntry:
    """Build a mock config entry."""
    backup_dir = overrides.pop(CONF_BACKUP_PATH, str(build_backup_dir(hass)))
    data = {
        **MOCK_USER_INPUT,
        CONF_FOLDER_ID: MOCK_FOLDER["id"],
        CONF_FOLDER_PATH: MOCK_FOLDER["path"],
        CONF_BACKUP_PATH: backup_dir,
        **overrides,
    }
    return MockConfigEntry(
        domain=DOMAIN,
        title="Resilio Sync (resilio.local)",
        data=data,
        options=options or {},
        unique_id=f"{data[CONF_HOST]}:{data[CONF_PORT]}",
    )


def build_agent_backup(
    backup_id: str = "backup1",
    *,
    date: str = "2026-08-30T23:00:00+00:00",
    size: int = 12,
) -> AgentBackup:
    """Create an AgentBackup for tests."""
    return AgentBackup(
        addons=[AddonInfo(name="Test Add-on", slug="test-addon", version="1.0.0")],
        backup_id=backup_id,
        date=date,
        database_included=True,
        extra_metadata={"resilio": True},
        folders=[Folder.SHARE],
        homeassistant_included=True,
        homeassistant_version="2026.8.3",
        name=f"Backup {backup_id}",
        protected=False,
        size=size,
    )


async def setup_integration(hass, aioclient_mock, **entry_overrides) -> MockConfigEntry:
    """Set up the integration with a fully loaded config entry."""
    options = entry_overrides.pop(
        "options",
        {
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        },
    )
    entry = build_mock_entry(
        hass,
        options=options,
        **entry_overrides,
    )
    entry.add_to_hass(hass)

    base_url = "http://resilio.local:8888/gui"
    mock_token_endpoint(aioclient_mock, base_url)
    aioclient_mock.get(
        f"{base_url}/",
        params={"action": "getsyncfolders"},
        json=webui_action({"folders": [MOCK_FOLDER]}),
    )
    aioclient_mock.get(
        f"{base_url}/",
        params={"action": "version"},
        json=webui_action({"value": "2.7.2.1370"}),
    )
    aioclient_mock.get(
        f"{base_url}/",
        params={"action": "getperformancewarnings"},
        json=webui_action({"warnings": []}),
    )

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    return entry
