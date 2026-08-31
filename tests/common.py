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
    CONF_MAX_BACKUPS,
    CONF_PRUNE_ENABLED,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_MAX_BACKUPS,
    DEFAULT_PORT,
    DEFAULT_PRUNE_ENABLED,
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
    "id": "folder123",
    "path": "C:\\Resilio\\Backups",
    "name": "Home Assistant Backups",
    "size": 2048,
    "files": 16,
    "peers": 3,
    "state": "in sync",
}

MOCK_OS = {"os": "windows", "version": "3.0"}


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
            CONF_MAX_BACKUPS: DEFAULT_MAX_BACKUPS,
            CONF_PRUNE_ENABLED: DEFAULT_PRUNE_ENABLED,
        },
    )
    entry = build_mock_entry(
        hass,
        options=options,
        **entry_overrides,
    )
    entry.add_to_hass(hass)

    base_url = "http://resilio.local:8888/api/v2"
    aioclient_mock.get(f"{base_url}/folders/{MOCK_FOLDER['id']}", json=MOCK_FOLDER)

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    return entry
