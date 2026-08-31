"""Config flow for Resilio Backup."""

from __future__ import annotations

import logging
from typing import Any, Self, override

import voluptuous as vol

from homeassistant import config_entries
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
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_MAX_BACKUPS,
    DEFAULT_PORT,
    DEFAULT_PRUNE_ENABLED,
    DEFAULT_USE_SSL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)

LOGGER = logging.getLogger(__name__)

CONF_FOLDER_CHOICE = "folder_choice"
CONF_NEW_FOLDER_PATH = "new_folder_path"
CREATE_NEW_VALUE = "__create_new__"


class ResilioBackupConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Resilio Backup."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._folder: dict[str, Any] = {}

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
                errors["base"] = "invalid_auth"
            except ResilioConnectionError:
                errors["base"] = "cannot_connect"
            # pylint: disable=broad-exception-caught
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected exception while connecting to Resilio")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                )
                self._abort_if_unique_id_configured()
                self._data = user_input
                return await self.async_step_folder()

        user_input = user_input or {
            CONF_HOST: "",
            CONF_PORT: DEFAULT_PORT,
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_USE_SSL: DEFAULT_USE_SSL,
            CONF_VERIFY_SSL: DEFAULT_VERIFY_SSL,
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=user_input[CONF_HOST]): str,
                    vol.Required(CONF_PORT, default=user_input[CONF_PORT]): int,
                    vol.Required(CONF_USERNAME, default=user_input[CONF_USERNAME]): str,
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Required(
                        CONF_USE_SSL, default=user_input[CONF_USE_SSL]
                    ): bool,
                    vol.Required(
                        CONF_VERIFY_SSL, default=user_input[CONF_VERIFY_SSL]
                    ): bool,
                }
            ),
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

        folder_choice_default = CREATE_NEW_VALUE if not folders else next(iter(folder_lookup))

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

        if user_input is not None:
            backup_path = str(user_input.get(CONF_BACKUP_PATH, "")).strip()
            if not backup_path:
                errors[CONF_BACKUP_PATH] = "required"
            else:
                return self.async_create_entry(
                    title=f"Resilio Sync ({self._data[CONF_HOST]})",
                    data={
                        **self._data,
                        CONF_FOLDER_ID: str(self._folder["id"]),
                        CONF_FOLDER_PATH: str(self._folder.get("path", "")),
                        CONF_BACKUP_PATH: backup_path,
                    },
                )

        return self.async_show_form(
            step_id="backup_path",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BACKUP_PATH,
                        default=str(self._folder.get("path", "")),
                    ): str,
                }
            ),
            errors=errors,
        )


class ResilioBackupOptionsFlow(config_entries.OptionsFlowWithReload):
    """Options flow for Resilio Backup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage integration options."""
        if user_input is not None:
            user_input[CONF_MAX_BACKUPS] = int(user_input[CONF_MAX_BACKUPS])
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
                }
            ),
        )
