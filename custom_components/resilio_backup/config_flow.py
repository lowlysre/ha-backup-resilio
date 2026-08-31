"""Config flow for Resilio Backup."""

from __future__ import annotations

import base64
import io
import logging
import re
from typing import Any, Self, override

import qrcode
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import ResilioApiClient, ResilioApiError, ResilioAuthError, ResilioConnectionError
from .const import (
    CONF_BACKUP_PATH,
    CONF_FOLDER_ID,
    CONF_FOLDER_PATH,
    CONF_MAX_BACKUPS,
    CONF_PRUNE_ENABLED,
    CONF_SCAN_INTERVAL,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_MAX_BACKUPS,
    DEFAULT_PORT,
    DEFAULT_PRUNE_ENABLED,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USE_SSL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

LOGGER = logging.getLogger(__name__)


def _render_qr_data_uri(link: str) -> str:
    """Render a link as a base64 PNG data URI, for embedding in a notification.

    Resilio's own WebUI draws its peer-invite QR client-side, from the same
    link text `getsynclink` returns (`app.js`'s `generateQRCode`); there's no
    server-side endpoint that returns a QR image. This does the same
    rendering here instead, off the event loop since `qrcode`/Pillow are
    both synchronous.
    """
    buffer = io.BytesIO()
    qrcode.make(link).save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{encoded}"


CONF_FOLDER_CHOICE = "folder_choice"
CONF_NEW_FOLDER_PATH = "new_folder_path"
CREATE_NEW_VALUE = "__create_new__"


def _strip_url_scheme(host: str) -> str:
    """Tolerate a full URL pasted into the host field instead of a bare host.

    ``ResilioClient`` builds its own ``scheme://host:port`` base URL, so a
    host like ``http://192.168.1.5/`` would otherwise double up into
    ``http://http://192.168.1.5/:8888/gui``. Strip a leading scheme and any
    trailing path/slash so users can paste the WebUI's own address as-is.
    """
    host = host.strip()
    host = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", host)
    return host.split("/", 1)[0]


class ResilioBackupConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Resilio Backup."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._folder: dict[str, Any] = {}
        self._pending_backup_path: str | None = None

    @staticmethod
    def _connection_schema(defaults: dict[str, Any]) -> vol.Schema:
        """Build the schema shared by the user, reauth, and reconfigure steps."""
        return vol.Schema(
            {
                vol.Required(CONF_HOST, default=defaults[CONF_HOST]): str,
                vol.Required(CONF_PORT, default=defaults[CONF_PORT]): int,
                vol.Required(CONF_USERNAME, default=defaults[CONF_USERNAME]): str,
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_USE_SSL, default=defaults[CONF_USE_SSL]): bool,
                vol.Required(CONF_VERIFY_SSL, default=defaults[CONF_VERIFY_SSL]): bool,
            }
        )

    async def _async_validate_connection(
        self, user_input: dict[str, Any]
    ) -> dict[str, str]:
        """Test a connection with the given input, returning any form errors."""
        user_input[CONF_HOST] = _strip_url_scheme(user_input[CONF_HOST])
        client = ResilioApiClient(
            self.hass,
            user_input[CONF_HOST],
            user_input[CONF_PORT],
            user_input[CONF_USERNAME],
            user_input[CONF_PASSWORD],
            user_input[CONF_USE_SSL],
            user_input[CONF_VERIFY_SSL],
        )
        try:
            await client.async_get_os()
        except ResilioAuthError:
            return {"base": "invalid_auth"}
        except ResilioConnectionError:
            return {"base": "cannot_connect"}
        # pylint: disable=broad-exception-caught
        except Exception:  # noqa: BLE001
            LOGGER.exception("Unexpected exception while connecting to Resilio")
            return {"base": "unknown"}
        return {}

    def _get_client(self) -> ResilioApiClient:
        """Build the API client from stored data."""
        return ResilioApiClient(
            self.hass,
            self._data[CONF_HOST],
            self._data[CONF_PORT],
            self._data[CONF_USERNAME],
            self._data[CONF_PASSWORD],
            self._data[CONF_USE_SSL],
            self._data[CONF_VERIFY_SSL],
        )

    @staticmethod
    @callback
    def async_get_options_flow(_config_entry) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return ResilioBackupOptionsFlow()

    def is_matching(self, _other_flow: Self) -> bool:
        """Return whether another flow matches this flow."""
        return False

    async def _async_get_folders(self) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """Fetch folders for the folder step."""
        try:
            return await self._get_client().async_get_folders(), {}
        except ResilioAuthError:
            return [], {"base": "invalid_auth"}
        except ResilioConnectionError:
            return [], {"base": "cannot_connect"}
        except ResilioApiError:
            return [], {"base": "unknown"}

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await self._async_validate_connection(user_input)
            if not errors:
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                )
                self._abort_if_unique_id_configured()
                self._data = user_input
                return await self.async_step_folder()

        defaults = user_input or {
            CONF_HOST: "",
            CONF_PORT: DEFAULT_PORT,
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_USE_SSL: DEFAULT_USE_SSL,
            CONF_VERIFY_SSL: DEFAULT_VERIFY_SSL,
        }

        return self.async_show_form(
            step_id="user",
            data_schema=self._connection_schema(defaults),
            errors=errors,
        )

    @override
    async def async_step_reauth(
        self, _entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when Resilio rejects our credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm re-authentication with updated credentials."""
        reauth_entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            new_data = {**reauth_entry.data, **user_input}
            errors = await self._async_validate_connection(new_data)
            if not errors:
                return self.async_update_reload_and_abort(
                    reauth_entry, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self._connection_schema(reauth_entry.data),
            errors=errors,
        )

    @override
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure connection details, then the synced folder and backup path.

        Validating the connection here just moves on to the same
        folder/backup_path steps the initial setup uses, pre-selecting the
        entry's current folder so a user who only wants to tweak the
        connection can click straight through unchanged.
        """
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await self._async_validate_connection(user_input)
            if not errors:
                new_unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                for entry in self.hass.config_entries.async_entries(DOMAIN):
                    if (
                        entry.entry_id != reconfigure_entry.entry_id
                        and entry.unique_id == new_unique_id
                    ):
                        return self.async_abort(reason="already_configured")
                self._data = {**reconfigure_entry.data, **user_input}
                self._folder = {
                    "id": reconfigure_entry.data.get(CONF_FOLDER_ID),
                    "path": reconfigure_entry.data.get(CONF_FOLDER_PATH),
                }
                return await self.async_step_folder()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._connection_schema(reconfigure_entry.data),
            errors=errors,
        )

    async def async_step_folder(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose an existing Resilio folder or start creating one."""
        folders, errors = await self._async_get_folders()
        folder_lookup = {str(folder["id"]): folder for folder in folders if "id" in folder}

        if user_input is not None:
            choice = user_input[CONF_FOLDER_CHOICE]
            if choice == CREATE_NEW_VALUE:
                return await self.async_step_new_folder()

            selected_folder = folder_lookup.get(choice)
            if selected_folder is None:
                errors["base"] = "no_folders"
            else:
                self._folder = selected_folder
                return await self.async_step_backup_path()

        if not folders and user_input is None and not errors:
            errors["base"] = "no_folders"

        current_folder_id = str(self._folder["id"]) if self._folder.get("id") else None
        if current_folder_id and current_folder_id in folder_lookup:
            # Reconfiguring an existing entry: default to its current folder.
            folder_choice_default = current_folder_id
        elif not folders:
            folder_choice_default = CREATE_NEW_VALUE
        else:
            folder_choice_default = next(iter(folder_lookup))

        return self.async_show_form(
            step_id="folder",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_FOLDER_CHOICE,
                        default=folder_choice_default,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                *[
                                    SelectOptionDict(
                                        value=str(folder["id"]),
                                        label=str(
                                            folder.get("name")
                                            or folder.get("path")
                                            or folder["id"]
                                        ),
                                    )
                                    for folder in folders
                                    if "id" in folder
                                ],
                                SelectOptionDict(
                                    value=CREATE_NEW_VALUE,
                                    label="Create a new folder",
                                ),
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_new_folder(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a new Resilio folder from a path."""
        errors: dict[str, str] = {}

        if user_input is not None:
            new_folder_path = str(user_input.get(CONF_NEW_FOLDER_PATH, "")).strip()
            if not new_folder_path:
                errors[CONF_NEW_FOLDER_PATH] = "required"
            else:
                try:
                    self._folder = await self._get_client().async_add_folder(new_folder_path)
                except ResilioAuthError:
                    errors["base"] = "invalid_auth"
                except ResilioConnectionError:
                    errors["base"] = "cannot_connect"
                except ResilioApiError:
                    errors["base"] = "unknown"
                else:
                    return await self.async_step_backup_path()

        return self.async_show_form(
            step_id="new_folder",
            data_schema=vol.Schema({vol.Required(CONF_NEW_FOLDER_PATH): str}),
            errors=errors,
        )

    async def async_step_backup_path(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose where backups are staged before syncing to the folder."""
        errors: dict[str, str] = {}
        folder_path = str(self._folder.get("path", ""))
        folder_name = str(self._folder.get("name") or folder_path or self._folder.get("id", ""))

        if user_input is not None:
            backup_path = str(user_input.get(CONF_BACKUP_PATH, "")).strip()
            if not backup_path:
                errors[CONF_BACKUP_PATH] = "required"
            elif (
                folder_path
                and backup_path != folder_path
                and backup_path != self._pending_backup_path
            ):
                # Backups written outside the synced folder won't actually
                # replicate to peers. Warn instead of blocking: remember
                # this value so a repeat submission is treated as confirmed.
                self._pending_backup_path = backup_path
                errors[CONF_BACKUP_PATH] = "path_mismatch"
            else:
                await self._async_notify_peer_invite()
                final_data = {
                    **self._data,
                    CONF_FOLDER_ID: str(self._folder["id"]),
                    CONF_FOLDER_PATH: folder_path,
                    CONF_BACKUP_PATH: backup_path,
                }
                if self.source == config_entries.SOURCE_RECONFIGURE:
                    return self.async_update_reload_and_abort(
                        self._get_reconfigure_entry(),
                        unique_id=f"{self._data[CONF_HOST]}:{self._data[CONF_PORT]}",
                        data=final_data,
                    )
                return self.async_create_entry(
                    title=f"Resilio Sync ({self._data[CONF_HOST]})",
                    data=final_data,
                )

        return self.async_show_form(
            step_id="backup_path",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BACKUP_PATH,
                        default=(user_input or {}).get(CONF_BACKUP_PATH)
                        or self._data.get(CONF_BACKUP_PATH)
                        or folder_path,
                    ): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "folder_name": folder_name,
                "folder_path": folder_path or "unknown",
            },
        )

    async def _async_notify_peer_invite(self) -> None:
        """Best-effort: post a notification with a peer-invite link for the folder.

        Not fatal if Resilio can't produce one (unlicensed agents, in
        particular, silently return an empty link for some folder/permission
        combinations); the config entry is created either way.
        """
        try:
            link = await self._get_client().async_get_share_link(
                str(self._folder["id"]), str(self._folder.get("name") or "Resilio Backups")
            )
        except ResilioApiError:
            LOGGER.debug("Could not generate a Resilio peer-invite link", exc_info=True)
            return

        if not link:
            return

        message = (
            "Share this link with another device to add it as a peer for "
            f"your Resilio Backup folder:\n\n{link}"
        )

        try:
            qr_data_uri = await self.hass.async_add_executor_job(_render_qr_data_uri, link)
        # pylint: disable=broad-exception-caught
        except Exception:  # noqa: BLE001
            LOGGER.debug("Could not render a QR code for the peer-invite link", exc_info=True)
        else:
            message += f"\n\n![Peer invite QR code]({qr_data_uri})"

        persistent_notification.async_create(
            self.hass,
            message,
            title="Resilio Backup: invite a peer",
            notification_id=f"{DOMAIN}_peer_invite_{self._folder['id']}",
        )


class ResilioBackupOptionsFlow(config_entries.OptionsFlowWithReload):
    """Options flow for Resilio Backup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage integration options."""
        if user_input is not None:
            user_input[CONF_MAX_BACKUPS] = int(user_input[CONF_MAX_BACKUPS])
            user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MAX_BACKUPS,
                        default=self.config_entry.options.get(
                            CONF_MAX_BACKUPS, DEFAULT_MAX_BACKUPS
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            mode=NumberSelectorMode.BOX,
                            step=1,
                        )
                    ),
                    vol.Required(
                        CONF_PRUNE_ENABLED,
                        default=self.config_entry.options.get(
                            CONF_PRUNE_ENABLED, DEFAULT_PRUNE_ENABLED
                        ),
                    ): bool,
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            mode=NumberSelectorMode.BOX,
                            step=1,
                            unit_of_measurement="seconds",
                        )
                    ),
                }
            ),
        )
