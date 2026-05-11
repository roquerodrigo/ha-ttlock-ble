"""Config flow for ttlock_ble."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.util import slugify

from .api import TtlockBleApiClient
from .const import DOMAIN, LOGGER
from .exceptions import (
    TtlockBleApiClientAuthenticationError,
    TtlockBleApiClientCommunicationError,
    TtlockBleApiClientError,
    TtlockBleApiClientVerificationRequiredError,
)
from .options_flow import TtlockBleOptionsFlow

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .data import (
        TtlockBleConfigData,
        TtlockBleConfigEntry,
        TtlockBleCredentialsInput,
        TtlockBleStoredKey,
        TtlockBleVerificationInput,
    )


CONF_VERIFICATION_CODE = "verification_code"


def _credentials_schema(default_username: str | None = None) -> vol.Schema:
    """Build the username/password schema, optionally pre-filled."""
    return vol.Schema(
        {
            vol.Required(
                CONF_USERNAME,
                default=default_username
                if default_username is not None
                else vol.UNDEFINED,
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT),
            ),
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD),
            ),
        },
    )


def _verification_schema() -> vol.Schema:
    """Build the verification-code schema for the second step."""
    return vol.Schema(
        {
            vol.Required(CONF_VERIFICATION_CODE): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT),
            ),
        },
    )


class TtlockBleFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for TTLock BLE."""

    VERSION = 1

    _username: str
    _password: str

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: TtlockBleConfigEntry,  # noqa: ARG004
    ) -> TtlockBleOptionsFlow:
        """Return the options flow handler."""
        return TtlockBleOptionsFlow()

    # The narrowed ``TtlockBleCredentialsInput`` parameter is intentional
    # — HA's base class declares ``dict[str, Any] | None`` here, and we trade
    # strict LSP compliance for stronger typing of our own user_input schema.
    async def async_step_user(  # type: ignore[override]
        self,
        user_input: TtlockBleCredentialsInput | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Collect credentials and either create the entry or branch to 2FA."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(slugify(user_input["username"]))
            self._abort_if_unique_id_configured()
            self._username = user_input["username"]
            self._password = user_input["password"]
            errors = await self._async_login_and_maybe_request_code()
            if not errors:
                return await self._async_finalize_create_entry()
            if errors.get("base") == "verification_required":
                return await self.async_step_verify_code()
        return self.async_show_form(
            step_id="user",
            data_schema=_credentials_schema(
                default_username=user_input["username"] if user_input else None,
            ),
            errors=errors,
        )

    async def async_step_verify_code(
        self,
        user_input: TtlockBleVerificationInput | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Submit the emailed code and complete login."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_validate_code_and_login(
                user_input["verification_code"],
            )
            if not errors:
                return await self._async_finalize_create_entry()
        return self.async_show_form(
            step_id="verify_code",
            data_schema=_verification_schema(),
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, str],  # noqa: ARG002
    ) -> config_entries.ConfigFlowResult:
        """Entry point when stored credentials are rejected by the cloud."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: TtlockBleCredentialsInput | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Prompt for new credentials and update the entry on success."""
        entry = self._get_reauth_entry()
        return await self._async_step_credentials_for_entry(
            entry,
            step_id="reauth_confirm",
            user_input=user_input,
        )

    async def async_step_reconfigure(
        self,
        user_input: TtlockBleCredentialsInput | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Allow editing credentials of an existing entry."""
        entry = self._get_reconfigure_entry()
        return await self._async_step_credentials_for_entry(
            entry,
            step_id="reconfigure",
            user_input=user_input,
        )

    async def _async_step_credentials_for_entry(
        self,
        entry: TtlockBleConfigEntry,
        *,
        step_id: str,
        user_input: TtlockBleCredentialsInput | None,
    ) -> config_entries.ConfigFlowResult:
        """Shared credential-prompt body for reauth + reconfigure."""
        errors: dict[str, str] = {}
        existing = cast("TtlockBleConfigData", cast("object", entry.data))
        if user_input is not None:
            self._username = user_input["username"]
            self._password = user_input["password"]
            errors = await self._async_login_for_existing_entry()
            if not errors:
                return await self._async_finalize_update_entry(entry)
        return self.async_show_form(
            step_id=step_id,
            data_schema=_credentials_schema(
                default_username=existing.get("username"),
            ),
            errors=errors,
        )

    async def _async_login_and_maybe_request_code(self) -> dict[str, str]:
        """Try the cloud login; on -1014 emit the verification code."""
        client = TtlockBleApiClient(httpx_client=get_async_client(self.hass))
        try:
            await client.async_login(self._username, self._password)
        except TtlockBleApiClientVerificationRequiredError as exc:
            LOGGER.info("Cloud requested new-device verification: %s", exc)
            return await self._async_request_verification_code(client)
        except TtlockBleApiClientAuthenticationError as exc:
            LOGGER.warning("Cloud login rejected: %s", exc)
            return {"base": "auth"}
        except TtlockBleApiClientCommunicationError as exc:
            LOGGER.error("Cloud login failed to reach TTLock: %s", exc)
            return {"base": "connection"}
        except TtlockBleApiClientError as exc:
            LOGGER.exception("Unknown cloud login error: %s", exc)
            return {"base": "unknown"}
        return {}

    async def _async_request_verification_code(
        self,
        client: TtlockBleApiClient,
    ) -> dict[str, str]:
        """Ask the cloud to email a verification code."""
        try:
            await client.async_request_verification_code(self._username)
        except TtlockBleApiClientCommunicationError as exc:
            LOGGER.error("Failed to request verification code: %s", exc)
            return {"base": "connection"}
        except TtlockBleApiClientError as exc:
            LOGGER.exception("Unknown error requesting verification code: %s", exc)
            return {"base": "unknown"}
        return {"base": "verification_required"}

    async def _async_validate_code_and_login(self, code: str) -> dict[str, str]:
        """Submit the verification code and complete login."""
        client = TtlockBleApiClient(httpx_client=get_async_client(self.hass))
        try:
            await client.async_validate_new_device_and_login(
                self._username,
                self._password,
                code,
            )
        except TtlockBleApiClientAuthenticationError as exc:
            LOGGER.warning("Verification code rejected: %s", exc)
            return {"base": "invalid_code"}
        except TtlockBleApiClientCommunicationError as exc:
            LOGGER.error("Failed to reach TTLock during verification: %s", exc)
            return {"base": "connection"}
        except TtlockBleApiClientError as exc:
            LOGGER.exception("Unknown verification error: %s", exc)
            return {"base": "unknown"}
        return {}

    async def _async_login_for_existing_entry(self) -> dict[str, str]:
        """Login path used by reauth/reconfigure (no 2FA branch)."""
        client = TtlockBleApiClient(httpx_client=get_async_client(self.hass))
        try:
            await client.async_login(self._username, self._password)
        except TtlockBleApiClientVerificationRequiredError as exc:
            LOGGER.warning(
                "Cloud asked for new-device verification on reauth — "
                "re-add the entry to complete it: %s",
                exc,
            )
            return {"base": "verification_required"}
        except TtlockBleApiClientAuthenticationError as exc:
            LOGGER.warning("Reauth/reconfigure login rejected: %s", exc)
            return {"base": "auth"}
        except TtlockBleApiClientCommunicationError as exc:
            LOGGER.error("Reauth/reconfigure failed to reach TTLock: %s", exc)
            return {"base": "connection"}
        except TtlockBleApiClientError as exc:
            LOGGER.exception("Unknown reauth/reconfigure error: %s", exc)
            return {"base": "unknown"}
        return {}

    async def _async_finalize_create_entry(self) -> config_entries.ConfigFlowResult:
        """Re-issue login + list keys, then create the entry."""
        keys = await self._async_fetch_keys()
        data: TtlockBleConfigData = {
            "username": self._username,
            "password": self._password,
            "keys": keys,
        }
        return self.async_create_entry(title=self._username, data=dict(data))

    async def _async_finalize_update_entry(
        self,
        entry: TtlockBleConfigEntry,
    ) -> config_entries.ConfigFlowResult:
        """Refresh keys and update an existing entry (reauth / reconfigure)."""
        keys = await self._async_fetch_keys()
        data: TtlockBleConfigData = {
            "username": self._username,
            "password": self._password,
            "keys": keys,
        }
        return self.async_update_reload_and_abort(entry, data_updates=dict(data))

    async def _async_fetch_keys(self) -> list[TtlockBleStoredKey]:
        """Login once more and pull the current key set from the cloud."""
        client = TtlockBleApiClient(httpx_client=get_async_client(self.hass))
        await client.async_login(self._username, self._password)
        virtual_keys = await client.async_list_keys()
        return [cast("TtlockBleStoredKey", key.to_dict()) for key in virtual_keys]
