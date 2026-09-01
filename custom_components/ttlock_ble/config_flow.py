"""Config flow for ttlock_ble."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers import selector
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.util import slugify

from .advertisement import decode_lock_advertisement
from .api import TtlockBleApiClient
from .const import DOMAIN, LOGGER
from .exceptions import (
    TtlockBleApiClientAuthenticationError,
    TtlockBleApiClientCommunicationError,
    TtlockBleApiClientError,
    TtlockBleApiClientVerificationRequiredError,
)
from .manual_key import TtlockBleManualKey
from .options_flow import TtlockBleOptionsFlow

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

    from ttlock_ble import LockAdvertisement

    from .data import (
        TtlockBleConfigData,
        TtlockBleConfigEntry,
        TtlockBleCredentialsInput,
        TtlockBleManualKeyInput,
        TtlockBleStoredKey,
        TtlockBleVerificationInput,
    )


CONF_VERIFICATION_CODE = "verification_code"
ABORT_ALREADY_CONFIGURED = "already_configured"
ABORT_NOT_A_LOCK = "not_a_lock"
DEFAULT_PROTOCOL_TYPE = 5
DEFAULT_PROTOCOL_VERSION = 3
DEFAULT_SCENE = 2
DEFAULT_GROUP_ID = 1
DEFAULT_ORG_ID = 1


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


def _manual_key_schema(
    defaults: TtlockBleManualKeyInput | None = None,
) -> vol.Schema:
    """Build the manual key schema, pre-filled when correcting a rejected form."""
    previous = cast("Mapping[str, str | int]", defaults or {})

    def _default(field: str, fallback: str | int) -> str | int:
        return previous.get(field, fallback)

    return vol.Schema(
        {
            vol.Required("lock_mac", default=_default("lock_mac", "")): (
                selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT),
                )
            ),
            vol.Required("aes_key", default=_default("aes_key", "")): (
                selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD,
                    ),
                )
            ),
            vol.Required("unlock_key", default=_default("unlock_key", "")): (
                selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD,
                    ),
                )
            ),
            vol.Optional("admin_passcode", default=_default("admin_passcode", "")): (
                selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD,
                    ),
                )
            ),
            vol.Optional("lock_name", default=_default("lock_name", "")): (
                selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT),
                )
            ),
            vol.Required(
                "protocol_type",
                default=_default("protocol_type", DEFAULT_PROTOCOL_TYPE),
            ): _positive_int_selector(),
            vol.Required(
                "protocol_version",
                default=_default("protocol_version", DEFAULT_PROTOCOL_VERSION),
            ): _positive_int_selector(),
            vol.Required("scene", default=_default("scene", DEFAULT_SCENE)): (
                _positive_int_selector()
            ),
            vol.Required(
                "group_id",
                default=_default("group_id", DEFAULT_GROUP_ID),
            ): _positive_int_selector(),
            vol.Required("org_id", default=_default("org_id", DEFAULT_ORG_ID)): (
                _positive_int_selector()
            ),
        },
    )


def _positive_int_selector() -> selector.NumberSelector:
    """Build the numeric selector used by every frame-header field."""
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=255,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
        ),
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
    _discovery: BluetoothServiceInfoBleak | None = None
    _discovered_advertisement: LockAdvertisement | None = None
    _discovered_name: str = ""

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
        user_input: TtlockBleCredentialsInput | None = None,  # noqa: ARG002
    ) -> config_entries.ConfigFlowResult:
        """Offer the two ways of obtaining a lock's keys."""
        return self.async_show_menu(step_id="user", menu_options=["cloud", "manual"])

    async def async_step_bluetooth(
        self,
        discovery_info: BluetoothServiceInfoBleak,
    ) -> config_entries.ConfigFlowResult:
        """
        Handle a lock the bluetooth manager heard advertise.

        The manifest matcher is the manufacturer id alone, which is the
        protocol header of a V3 lock and nothing more specific; the
        decode plus the address cross-check is what separates a real
        lock from anything else that happens to broadcast under it.
        """
        advertisement = decode_lock_advertisement(
            discovery_info.address,
            discovery_info.manufacturer_data,
        )
        if advertisement is None:
            return self.async_abort(reason=ABORT_NOT_A_LOCK)
        await self.async_set_unique_id(format_mac(discovery_info.address))
        self._abort_if_unique_id_configured()
        self._abort_if_lock_configured(discovery_info.address)
        self._discovery = discovery_info
        self._discovered_advertisement = advertisement
        self._discovered_name = discovery_info.name or discovery_info.address
        self.context["title_placeholders"] = {"name": self._discovered_name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self,
        user_input: TtlockBleCredentialsInput | None = None,  # noqa: ARG002
    ) -> config_entries.ConfigFlowResult:
        """
        Offer the two key routes for a lock that was found, not typed in.

        Discovery hands over the address and the frame header, never the
        AES and unlock keys — those exist only in a TTLock account or in
        whatever provisioned the lock locally. So this is the same menu
        the manual entry point shows, with the lock already identified.
        """
        return self.async_show_menu(
            step_id="bluetooth_confirm",
            menu_options=["cloud", "manual"],
            description_placeholders={"name": self._discovered_name},
        )

    async def async_step_cloud(
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
                created, errors = await self._async_finalize_create_entry()
                if created is not None:
                    return created
            if errors.get("base") == "verification_required":
                return await self.async_step_verify_code()
        return self.async_show_form(
            step_id="cloud",
            data_schema=_credentials_schema(
                default_username=user_input["username"] if user_input else None,
            ),
            errors=errors,
        )

    async def async_step_manual(
        self,
        user_input: TtlockBleManualKeyInput | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Take a key obtained outside the cloud and create the entry from it."""
        errors: dict[str, str] = {}
        if user_input is not None:
            manual_key = TtlockBleManualKey(self.hass)
            errors = manual_key.async_validate(user_input)
            if not errors:
                key = manual_key.build(user_input)
                await self.async_set_unique_id(format_mac(key.lockMac))
                self._abort_if_unique_id_configured()
                self._abort_if_lock_configured(key.lockMac)
                data: TtlockBleConfigData = {
                    "keys": [cast("TtlockBleStoredKey", key.to_dict())],
                }
                return self.async_create_entry(
                    title=key.lockAlias,
                    data=dict(data),
                )
        return self.async_show_form(
            step_id="manual",
            data_schema=_manual_key_schema(user_input or self._discovered_defaults()),
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
                created, errors = await self._async_finalize_create_entry()
                if created is not None:
                    return created
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
        """Allow editing an existing entry, by whichever route created it."""
        entry = self._get_reconfigure_entry()
        existing = cast("TtlockBleConfigData", cast("object", entry.data))
        if "username" not in existing:
            return await self.async_step_reconfigure_manual()
        return await self._async_step_credentials_for_entry(
            entry,
            step_id="reconfigure",
            user_input=user_input,
        )

    async def async_step_reconfigure_manual(
        self,
        user_input: TtlockBleManualKeyInput | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Correct the key of an entry that was created from a manual one."""
        entry = self._get_reconfigure_entry()
        existing = cast("TtlockBleConfigData", cast("object", entry.data))
        errors: dict[str, str] = {}
        manual_key = TtlockBleManualKey(self.hass)
        if user_input is not None:
            errors = manual_key.async_validate(user_input)
            if not errors:
                key = manual_key.build(user_input)
                # The MAC is editable here, and it is this entry's unique id —
                # correcting a typo has to move the id with it, or the old one
                # keeps squatting and blocks re-adding the real lock.
                self._abort_if_lock_configured(
                    key.lockMac,
                    ignore_entry_id=entry.entry_id,
                )
                data: TtlockBleConfigData = {
                    "keys": [cast("TtlockBleStoredKey", key.to_dict())],
                }
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=format_mac(key.lockMac),
                    data_updates=dict(data),
                    title=key.lockAlias,
                )
        return self.async_show_form(
            step_id="reconfigure_manual",
            data_schema=_manual_key_schema(
                user_input or manual_key.defaults_from(existing["keys"][0]),
            ),
            errors=errors,
        )

    @callback
    def _discovered_defaults(self) -> TtlockBleManualKeyInput | None:
        """
        Pre-fill the manual form with everything the advertisement already said.

        The address, the name and three of the five frame-header
        integers come off the air, so what is left to type is what only
        the owner has. It also removes the class of typo the header
        cross-check exists to catch.
        """
        if self._discovery is None or self._discovered_advertisement is None:
            return None
        return {
            "lock_mac": self._discovery.address,
            "aes_key": "",
            "unlock_key": "",
            "admin_passcode": "",
            "lock_name": self._discovery.name or "",
            "protocol_type": self._discovered_advertisement.protocol_type,
            "protocol_version": self._discovered_advertisement.protocol_version,
            "scene": self._discovered_advertisement.scene,
            "group_id": DEFAULT_GROUP_ID,
            "org_id": DEFAULT_ORG_ID,
        }

    @callback
    def _discovered_lock_missing_from(
        self,
        keys: list[TtlockBleStoredKey],
    ) -> dict[str, str]:
        """
        Refuse an account that does not hold the lock the discovery was about.

        The flow was started from a card naming one lock; an account
        without it would silently create an entry for a different set of
        locks and leave the discovered one still unconfigured.
        """
        if self._discovery is None:
            return {}
        target = format_mac(self._discovery.address)
        if any(format_mac(key["lockMac"]) == target for key in keys):
            return {}
        LOGGER.warning(
            "The account holds no key for the discovered lock %s",
            self._discovery.address,
        )
        return {"base": "lock_not_in_account"}

    @callback
    def _abort_if_lock_configured(
        self,
        lock_mac: str,
        *,
        ignore_entry_id: str | None = None,
    ) -> None:
        """
        Abort when some existing entry already carries this lock.

        The unique id alone does not catch it: an entry created from a
        cloud account is keyed by the account, so the same lock arriving
        by hand would otherwise be accepted and then collide on entity
        unique ids, leaving the second entry silently without entities.

        `ignore_entry_id` skips the entry being reconfigured, which of
        course already holds its own lock.
        """
        target = format_mac(lock_mac)
        for entry in self._async_current_entries(include_ignore=False):
            if entry.entry_id == ignore_entry_id:
                continue
            existing = cast("TtlockBleConfigData", cast("object", entry.data))
            for key in existing.get("keys", []):
                if format_mac(key["lockMac"]) == target:
                    raise AbortFlow(ABORT_ALREADY_CONFIGURED)

    @callback
    def _abort_if_any_lock_configured(
        self,
        keys: list[TtlockBleStoredKey],
        *,
        ignore_entry_id: str | None = None,
    ) -> None:
        """Run the per-lock collision check across a whole fetched key set."""
        for key in keys:
            self._abort_if_lock_configured(
                key["lockMac"],
                ignore_entry_id=ignore_entry_id,
            )

    async def _async_step_credentials_for_entry(
        self,
        entry: TtlockBleConfigEntry,
        *,
        step_id: str,
        user_input: TtlockBleCredentialsInput | None,
    ) -> config_entries.ConfigFlowResult:
        """
        Shared credential-prompt body for reauth + reconfigure.

        The entry is keyed by the account, so credentials for a
        *different* account are not a re-authentication: accepting them
        would repoint the entry at a second set of locks and leave the
        original account's unique id unreachable for a fresh entry.
        """
        errors: dict[str, str] = {}
        existing = cast("TtlockBleConfigData", cast("object", entry.data))
        if user_input is not None:
            await self.async_set_unique_id(slugify(user_input["username"]))
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            self._username = user_input["username"]
            self._password = user_input["password"]
            errors = await self._async_login_for_existing_entry()
            if not errors:
                updated, errors = await self._async_finalize_update_entry(entry)
                if updated is not None:
                    return updated
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

    async def _async_finalize_create_entry(
        self,
    ) -> tuple[config_entries.ConfigFlowResult | None, dict[str, str]]:
        """Re-issue login + list keys, then create the entry."""
        keys, errors = await self._async_fetch_keys()
        if errors:
            return None, errors
        missing = self._discovered_lock_missing_from(keys)
        if missing:
            return None, missing
        self._abort_if_any_lock_configured(keys)
        data: TtlockBleConfigData = {
            "username": self._username,
            "password": self._password,
            "keys": keys,
        }
        return self.async_create_entry(title=self._username, data=dict(data)), {}

    async def _async_finalize_update_entry(
        self,
        entry: TtlockBleConfigEntry,
    ) -> tuple[config_entries.ConfigFlowResult | None, dict[str, str]]:
        """Refresh keys and update an existing entry (reauth / reconfigure)."""
        keys, errors = await self._async_fetch_keys()
        if errors:
            return None, errors
        self._abort_if_any_lock_configured(keys, ignore_entry_id=entry.entry_id)
        data: TtlockBleConfigData = {
            "username": self._username,
            "password": self._password,
            "keys": keys,
        }
        return self.async_update_reload_and_abort(entry, data_updates=dict(data)), {}

    async def _async_fetch_keys(
        self,
    ) -> tuple[list[TtlockBleStoredKey], dict[str, str]]:
        """
        Login once more and pull the current key set from the cloud.

        Mapped to form errors like every sibling cloud call: this one
        runs after the credentials (and possibly a verification code)
        were already accepted, so letting a network blip escape would
        discard that work behind a generic error dialog instead of
        re-showing the form.
        """
        client = TtlockBleApiClient(httpx_client=get_async_client(self.hass))
        try:
            await client.async_login(self._username, self._password)
            virtual_keys = await client.async_list_keys()
        except TtlockBleApiClientAuthenticationError as exc:
            LOGGER.warning("Cloud rejected the login while listing keys: %s", exc)
            return [], {"base": "auth"}
        except TtlockBleApiClientCommunicationError as exc:
            LOGGER.error("Failed to reach TTLock while listing keys: %s", exc)
            return [], {"base": "connection"}
        except TtlockBleApiClientError as exc:
            LOGGER.exception("Unknown error listing keys: %s", exc)
            return [], {"base": "unknown"}
        return [cast("TtlockBleStoredKey", key.to_dict()) for key in virtual_keys], {}
