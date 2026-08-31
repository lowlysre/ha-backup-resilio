"""Tests for the Resilio config flow."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
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
    CONF_SCAN_INTERVAL,
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
    assert result["description_placeholders"] == {
        "folder_name": MOCK_FOLDER["name"],
        "folder_path": MOCK_FOLDER["path"],
    }

    # A path outside the Resilio folder warns instead of blocking...
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BACKUP_PATH: "C:\\HA\\Backups"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_BACKUP_PATH: "path_mismatch"}

    # ...and a repeat submission of the same path confirms it.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BACKUP_PATH: "C:\\HA\\Backups"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_FOLDER_ID] == MOCK_FOLDER["id"]
    assert result["data"][CONF_FOLDER_PATH] == MOCK_FOLDER["path"]
    assert result["data"][CONF_BACKUP_PATH] == "C:\\HA\\Backups"
    mock_client.add_folder.assert_not_awaited()
    mock_client.get_share_link.assert_awaited_once()


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


async def test_config_flow_strips_url_scheme_from_host(hass, mock_client) -> None:
    """A pasted URL in the host field is tolerated, not rejected."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**MOCK_USER_INPUT, "host": "http://192.168.86.155/"}
    )
    assert result["step_id"] == "folder"
    mock_client.get_os.assert_awaited_once()

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"folder_choice": MOCK_FOLDER["id"]}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BACKUP_PATH: MOCK_FOLDER["path"]}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == "192.168.86.155"


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
    """The options flow stores retention and polling settings."""
    entry = build_mock_entry(hass)
    entry.add_to_hass(hass)

    with patch.object(hass.config_entries, "async_schedule_reload") as schedule_reload:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_MAX_BACKUPS: 3,
                CONF_PRUNE_ENABLED: False,
                CONF_SCAN_INTERVAL: 120,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_MAX_BACKUPS: 3,
        CONF_PRUNE_ENABLED: False,
        CONF_SCAN_INTERVAL: 120,
    }
    schedule_reload.assert_called_once_with(entry.entry_id)


def test_is_matching_returns_false() -> None:
    """The flow never deduplicates against another in-progress flow."""
    assert ResilioBackupConfigFlow().is_matching(ResilioBackupConfigFlow()) is False


async def test_reauth_flow_happy_path(hass, mock_client) -> None:
    """A successful reauth updates stored credentials and reloads the entry."""
    assert mock_client is not None
    entry = build_mock_entry(hass)
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch.object(hass.config_entries, "async_schedule_reload") as schedule_reload:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "admin", CONF_PASSWORD: "new-secret"},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-secret"
    schedule_reload.assert_called_once_with(entry.entry_id)


@pytest.mark.parametrize(
    ("side_effect", "expected_error"),
    [
        (ResilioAuthError("bad auth"), "invalid_auth"),
        (ResilioConnectionError("down"), "cannot_connect"),
    ],
)
async def test_reauth_flow_errors(hass, mock_client, side_effect, expected_error) -> None:
    """Rejected or unreachable credentials surface as reauth step errors."""
    entry = build_mock_entry(hass)
    entry.add_to_hass(hass)
    mock_client.get_os.side_effect = side_effect

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "admin", CONF_PASSWORD: "wrong"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}


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


async def test_backup_path_mismatch_allows_different_path_on_confirm(hass, mock_client) -> None:
    """Confirming a mismatched path a second time uses that path, not the folder's."""
    assert mock_client is not None
    flow = build_flow(hass)
    setattr(flow, "_folder", MOCK_FOLDER)

    first = await flow.async_step_backup_path({CONF_BACKUP_PATH: "C:\\Elsewhere"})
    assert first["errors"] == {CONF_BACKUP_PATH: "path_mismatch"}

    second = await flow.async_step_backup_path({CONF_BACKUP_PATH: "C:\\Elsewhere"})
    assert second["type"] is FlowResultType.CREATE_ENTRY
    assert second["data"][CONF_BACKUP_PATH] == "C:\\Elsewhere"


async def test_backup_path_mismatch_resets_on_different_value(hass, mock_client) -> None:
    """Changing the path after a warning re-triggers the mismatch check."""
    assert mock_client is not None
    flow = build_flow(hass)
    setattr(flow, "_folder", MOCK_FOLDER)

    first = await flow.async_step_backup_path({CONF_BACKUP_PATH: "C:\\Elsewhere"})
    assert first["errors"] == {CONF_BACKUP_PATH: "path_mismatch"}

    second = await flow.async_step_backup_path({CONF_BACKUP_PATH: "C:\\SomewhereElse"})
    assert second["errors"] == {CONF_BACKUP_PATH: "path_mismatch"}


async def test_backup_path_matching_folder_skips_warning(hass, mock_client) -> None:
    """A backup path that already matches the folder's path needs no confirmation."""
    assert mock_client is not None
    flow = build_flow(hass)
    setattr(flow, "_folder", MOCK_FOLDER)

    result = await flow.async_step_backup_path({CONF_BACKUP_PATH: MOCK_FOLDER["path"]})

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_backup_path_posts_peer_invite_notification(hass, mock_client) -> None:
    """A non-empty share link is surfaced as a persistent notification with a QR code."""
    mock_client.get_share_link.return_value = "https://link.resilio.com/#f=test"
    flow = build_flow(hass)
    setattr(flow, "_folder", MOCK_FOLDER)

    with patch(
        "custom_components.resilio_backup.config_flow.persistent_notification.async_create"
    ) as notify:
        result = await flow.async_step_backup_path({CONF_BACKUP_PATH: MOCK_FOLDER["path"]})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    notify.assert_called_once()
    message = notify.call_args.args[1]
    assert "https://link.resilio.com/#f=test" in message
    assert "![Peer invite QR code](data:image/png;base64," in message


async def test_backup_path_peer_invite_failure_does_not_block_entry(hass, mock_client) -> None:
    """A failed share-link fetch doesn't prevent the entry from being created."""
    mock_client.get_share_link.side_effect = ResilioApiError("boom")
    flow = build_flow(hass)
    setattr(flow, "_folder", MOCK_FOLDER)

    with patch(
        "custom_components.resilio_backup.config_flow.persistent_notification.async_create"
    ) as notify:
        result = await flow.async_step_backup_path({CONF_BACKUP_PATH: MOCK_FOLDER["path"]})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    notify.assert_not_called()


async def test_backup_path_empty_share_link_skips_notification(hass, mock_client) -> None:
    """An empty share link (Resilio declining to mint one) posts no notification."""
    mock_client.get_share_link.return_value = ""
    flow = build_flow(hass)
    setattr(flow, "_folder", MOCK_FOLDER)

    with patch(
        "custom_components.resilio_backup.config_flow.persistent_notification.async_create"
    ) as notify:
        result = await flow.async_step_backup_path({CONF_BACKUP_PATH: MOCK_FOLDER["path"]})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    notify.assert_not_called()


async def test_backup_path_qr_render_failure_still_posts_link(hass, mock_client) -> None:
    """A QR rendering failure still posts the link, just without an image."""
    mock_client.get_share_link.return_value = "https://link.resilio.com/#f=test"
    flow = build_flow(hass)
    setattr(flow, "_folder", MOCK_FOLDER)

    with (
        patch(
            "custom_components.resilio_backup.config_flow.persistent_notification.async_create"
        ) as notify,
        patch(
            "custom_components.resilio_backup.config_flow._render_qr_data_uri",
            side_effect=RuntimeError("boom"),
        ),
    ):
        result = await flow.async_step_backup_path({CONF_BACKUP_PATH: MOCK_FOLDER["path"]})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    notify.assert_called_once()
    message = notify.call_args.args[1]
    assert "https://link.resilio.com/#f=test" in message
    assert "data:image/png;base64" not in message


async def test_reauth_flow_updates_credentials(hass, mock_client) -> None:
    """Reauth validates and stores updated credentials, then reloads the entry."""
    assert mock_client is not None
    entry = build_mock_entry(hass)
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    with patch.object(hass.config_entries, "async_schedule_reload") as schedule_reload:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**MOCK_USER_INPUT, "password": "new-secret"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new-secret"
    schedule_reload.assert_called_once_with(entry.entry_id)


async def test_reauth_flow_invalid_auth(hass, mock_client) -> None:
    """Reauth surfaces invalid credentials instead of updating the entry."""
    mock_client.get_os.side_effect = ResilioAuthError("bad auth")
    entry = build_mock_entry(hass)
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**MOCK_USER_INPUT, "password": "wrong"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data["password"] != "wrong"


async def test_reconfigure_flow_updates_connection(hass, mock_client) -> None:
    """Reconfigure validates and stores updated connection details."""
    assert mock_client is not None
    entry = build_mock_entry(hass)
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    with patch.object(hass.config_entries, "async_schedule_reload") as schedule_reload:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**MOCK_USER_INPUT, "host": "new-resilio.local"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == "new-resilio.local"
    assert entry.unique_id == f"new-resilio.local:{entry.data['port']}"
    schedule_reload.assert_called_once_with(entry.entry_id)


async def test_reconfigure_flow_already_configured(hass, mock_client) -> None:
    """Reconfiguring onto an endpoint already used by another entry aborts."""
    assert mock_client is not None
    entry = build_mock_entry(hass)
    entry.add_to_hass(hass)
    other_entry = build_mock_entry(hass, host="other.local")
    other_entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**MOCK_USER_INPUT, "host": "other.local"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_flow_cannot_connect(hass, mock_client) -> None:
    """Reconfigure surfaces connection failures."""
    mock_client.get_os.side_effect = ResilioConnectionError("down")
    entry = build_mock_entry(hass)
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MOCK_USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
