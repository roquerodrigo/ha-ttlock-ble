"""Config flow for integration_blueprint."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.util import slugify

from .api import IntegrationBlueprintApiClient
from .const import DOMAIN, LOGGER
from .exceptions import (
    IntegrationBlueprintApiClientAuthenticationError,
    IntegrationBlueprintApiClientCommunicationError,
    IntegrationBlueprintApiClientError,
)
from .options_flow import IntegrationBlueprintOptionsFlow

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .data import IntegrationBlueprintConfigData, IntegrationBlueprintConfigEntry


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


class IntegrationBlueprintFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Integration Blueprint."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: IntegrationBlueprintConfigEntry,  # noqa: ARG004
    ) -> IntegrationBlueprintOptionsFlow:
        """Return the options flow handler."""
        return IntegrationBlueprintOptionsFlow()

    # The narrowed ``IntegrationBlueprintConfigData`` parameter is intentional
    # — HA's base class declares ``dict[str, Any] | None`` here, and we trade
    # strict LSP compliance for stronger typing of our own user_input schema.
    async def async_step_user(  # type: ignore[override]
        self,
        user_input: IntegrationBlueprintConfigData | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await self._validate(user_input)
            if not errors:
                await self.async_set_unique_id(slugify(user_input["username"]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input["username"],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_credentials_schema(
                default_username=user_input["username"] if user_input else None,
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, str],  # noqa: ARG002
    ) -> config_entries.ConfigFlowResult:
        """Trigger reauth when the API rejects stored credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: IntegrationBlueprintConfigData | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Prompt the user for new credentials and update the entry."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        existing = cast("IntegrationBlueprintConfigData", entry.data)

        if user_input is not None:
            errors = await self._validate(user_input)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=dict(user_input),
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_credentials_schema(
                default_username=existing.get("username"),
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: IntegrationBlueprintConfigData | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Allow editing credentials of an existing entry."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        existing = cast("IntegrationBlueprintConfigData", entry.data)

        if user_input is not None:
            errors = await self._validate(user_input)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=dict(user_input),
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_credentials_schema(
                default_username=existing.get("username"),
            ),
            errors=errors,
        )

    async def _validate(
        self,
        user_input: IntegrationBlueprintConfigData,
    ) -> dict[str, str]:
        """Test credentials and return an errors dict (empty on success)."""
        try:
            await self._test_credentials(
                username=user_input["username"],
                password=user_input["password"],
            )
        except IntegrationBlueprintApiClientAuthenticationError as exception:
            LOGGER.warning(exception)
            return {"base": "auth"}
        except IntegrationBlueprintApiClientCommunicationError as exception:
            LOGGER.error(exception)
            return {"base": "connection"}
        except IntegrationBlueprintApiClientError as exception:
            LOGGER.exception(exception)
            return {"base": "unknown"}
        return {}

    async def _test_credentials(self, username: str, password: str) -> None:
        """Validate credentials against the API."""
        client = IntegrationBlueprintApiClient(
            username=username,
            password=password,
            session=async_create_clientsession(self.hass),
        )
        await client.async_get_data()
