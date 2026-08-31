"""Tests for the Resilio config flow."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from homeassistant.data_entry_flow import FlowResultType

from custom_components.resilio_backup.api import (
    ResilioApiError,
    ResilioAuthError,
    ResilioConnectionError,
)
from custom_components.resilio_backup.config_flow import (
    CREATE_NEW_VALUE,
    ResilioBackupConfigFlow,
)
from custom_components.resilio_backup.const import (
    CONF_BACKUP_PATH,
    CONF_FOLDER_ID,
    CONF_FOLDER_PATH,
    CONF_MAX_BACKUPS,
    CONF_PRUNE_ENABLED,
    DOMAIN,
)
from tests.common import MOCK_FOLDER, MOCK_USER_INPUT, build_mock_entry


def build_flow(hass) -> ResilioBackupConfigFlow:
    """Build a flow with stored user credentials for direct step tests."""
    flow = ResilioBackupConfigFlow()
    flow.hass = hass
    flow.context = {}
    setattr(flow, "_data", MOCK_USER_INPUT)
    return flow


async def test_config_flow_existing_folder(hass, mock_client) -> None:
    """The flow creates an entry from an existing folder."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MOCK_USER_INPUT
    )
    assert result["step_id"] == "folder"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"folder_choice": MOCK_FOLDER["id"]}
    )
    assert result["step_id"] == "backup_path"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BACKUP_PATH: "C:\\HA\\Backups"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_FOLDER_ID] == MOCK_FOLDER["id"]
    assert result["data"][CONF_FOLDER_PATH] == MOCK_FOLDER["path"]
    assert result["data"][CONF_BACKUP_PATH] == "C:\\HA\\Backups"
    mock_client.add_folder.assert_not_awaited()


async def test_config_flow_create_new_folder(hass, mock_client) -> None:
    """The flow can create a new Resilio folder."""
    created_folder = {**MOCK_FOLDER, "id": "newfolder", "path": "D:\\Sync\\Backups"}
    mock_client.add_folder.return_value = created_folder

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MOCK_USER_INPUT
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"folder_choice": CREATE_NEW_VALUE}
    )
    assert result["step_id"] == "new_folder"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"new_folder_path": "D:\\Sync\\Backups"}
    )
    assert result["step_id"] == "backup_path"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BACKUP_PATH: "D:\\Sync\\Backups"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_FOLDER_ID] == "newfolder"
    mock_client.add_folder.assert_awaited_once_with("D:\\Sync\\Backups")


async def test_config_flow_cannot_connect(hass, mock_client) -> None:
    """Connection errors surface to the user."""
    mock_client.get_os.side_effect = ResilioConnectionError("down")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MOCK_USER_INPUT
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_config_flow_invalid_auth(hass, mock_client) -> None:
    """Auth errors surface to the user."""
    mock_client.get_os.side_effect = ResilioAuthError("bad auth")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MOCK_USER_INPUT
    )
    assert result["errors"] == {"base": "invalid_auth"}


async def test_config_flow_unknown_error(hass, mock_client) -> None:
    """Unexpected errors map to unknown."""
    mock_client.get_os.side_effect = RuntimeError("boom")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MOCK_USER_INPUT
    )
    assert result["errors"] == {"base": "unknown"}


async def test_config_flow_already_configured(hass, mock_client) -> None:
    """Duplicate host and port abort."""
    build_mock_entry(hass).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MOCK_USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_client.get_os.assert_awaited_once()


async def test_config_flow_no_folders(hass, mock_client) -> None:
    """An empty folder list surfaces the create-new guidance."""
    mock_client.get_folders.return_value = []
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MOCK_USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_folders"}
    mock_client.get_folders.assert_awaited_once()


async def test_options_flow_happy_path(hass) -> None:
    """The options flow stores retention settings."""
    entry = build_mock_entry(hass)
    entry.add_to_hass(hass)

    with patch.object(hass.config_entries, "async_schedule_reload") as schedule_reload:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_MAX_BACKUPS: 3,
                CONF_PRUNE_ENABLED: False,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_MAX_BACKUPS: 3,
        CONF_PRUNE_ENABLED: False,
    }
    schedule_reload.assert_called_once_with(entry.entry_id)


def test_is_matching_returns_false() -> None:
    """The flow never deduplicates against another in-progress flow."""
    assert ResilioBackupConfigFlow().is_matching(ResilioBackupConfigFlow()) is False


@pytest.mark.parametrize(
    ("side_effect", "expected_error"),
    [
        (ResilioAuthError("bad auth"), "invalid_auth"),
        (ResilioConnectionError("down"), "cannot_connect"),
    ],
)
async def test_folder_step_connection_errors(hass, mock_client, side_effect, expected_error) -> None:
    """Folder fetch failures surface as step errors."""
    mock_client.get_folders.side_effect = side_effect

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], MOCK_USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}


async def test_folder_step_unknown_api_error(hass, mock_client) -> None:
    """Folder fetch API errors surface as unknown."""
    assert mock_client is not None
    mock_client.get_folders.side_effect = ResilioApiError("boom")

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], MOCK_USER_INPUT)

    assert result["errors"] == {"base": "unknown"}


async def test_folder_step_requires_backup_path(hass, mock_client) -> None:
    """Backup path is validated before entry creation."""
    assert mock_client is not None
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.config_entries.flow.async_configure(result["flow_id"], MOCK_USER_INPUT)

    flow = build_flow(hass)
    setattr(flow, "_folder", MOCK_FOLDER)
    result = await flow.async_step_backup_path({})

    assert result["errors"] == {"backup_path": "required"}
    backup_field = next(
        key for key in result["data_schema"].schema if getattr(key, "schema", None) == "backup_path"
    )
    assert backup_field.default() == MOCK_FOLDER["path"]


async def test_folder_step_requires_new_folder_path(hass, mock_client) -> None:
    """Create-new requires a path."""
    assert mock_client is not None
    flow = build_flow(hass)

    result = await flow.async_step_new_folder({})

    assert result["errors"] == {"new_folder_path": "required"}


async def test_folder_step_invalid_existing_choice(hass, mock_client) -> None:
    """Unknown folder ids fail validation."""
    assert mock_client is not None
    flow = build_flow(hass)

    result = await flow.async_step_folder({"folder_choice": "missing"})

    assert result["errors"] == {"base": "no_folders"}


@pytest.mark.parametrize(
    ("side_effect", "expected_error"),
    [
        (ResilioAuthError("bad auth"), "invalid_auth"),
        (ResilioConnectionError("down"), "cannot_connect"),
        (ResilioApiError("boom"), "unknown"),
    ],
)
async def test_folder_step_create_new_errors(hass, mock_client, side_effect, expected_error) -> None:
    """Create-new surfaces API failures."""
    mock_client.add_folder.side_effect = side_effect
    flow = build_flow(hass)

    result = await flow.async_step_new_folder({"new_folder_path": "D:\\Sync\\Backups"})

    assert result["errors"] == {"base": expected_error}
