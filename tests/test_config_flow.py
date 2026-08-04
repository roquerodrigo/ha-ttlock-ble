from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ttlock_ble.const import DOMAIN
from custom_components.ttlock_ble.exceptions import (
    TtlockBleApiClientAuthenticationError,
    TtlockBleApiClientCommunicationError,
    TtlockBleApiClientError,
    TtlockBleApiClientVerificationRequiredError,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from ttlock_ble import VirtualKey


USER_INPUT = {"username": "user@example.com", "password": "pass"}
NEW_INPUT = {"username": "user@example.com", "password": "newpass"}
CODE_INPUT = {"verification_code": "123456"}


@contextmanager
def _patch_client(
    *,
    list_keys: list[VirtualKey] | None = None,
    login_side_effect: Exception | None = None,
    request_code_side_effect: Exception | None = None,
    validate_side_effect: Exception | None = None,
) -> Iterator[MagicMock]:
    with patch("custom_components.ttlock_ble.config_flow.TtlockBleApiClient") as cls:
        instance = MagicMock()
        instance.async_login = AsyncMock(side_effect=login_side_effect)
        instance.async_request_verification_code = AsyncMock(
            side_effect=request_code_side_effect,
        )
        instance.async_validate_new_device_and_login = AsyncMock(
            side_effect=validate_side_effect,
        )
        instance.async_list_keys = AsyncMock(return_value=list_keys or [])
        cls.return_value = instance
        yield instance


async def _start_menu(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def _start_user_flow(hass):
    """Open the flow and pick the cloud branch, where most tests start."""
    menu = await _start_menu(hass)
    return await hass.config_entries.flow.async_configure(
        menu["flow_id"], user_input={"next_step_id": "cloud"}
    )


def _existing_entry(hass, *, username: str = "user@example.com") -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": username, "password": "pass", "keys": []},
        unique_id="user_example_com",
    )
    entry.add_to_hass(hass)
    return entry


# --- User step -------------------------------------------------------------


async def test_step_user_offers_both_routes(hass, enable_custom_integrations) -> None:
    result = await _start_menu(hass)
    assert result["type"] == FlowResultType.MENU
    assert result["menu_options"] == ["cloud", "manual"]


async def test_step_cloud_shows_form(hass, enable_custom_integrations) -> None:
    result = await _start_user_flow(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "cloud"


async def test_step_user_success_creates_entry(
    hass,
    enable_custom_integrations,
    sample_virtual_key,
) -> None:
    with _patch_client(list_keys=[sample_virtual_key]):
        flow = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=USER_INPUT
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == USER_INPUT["username"]
    assert result["data"]["username"] == USER_INPUT["username"]
    assert result["data"]["password"] == USER_INPUT["password"]
    assert len(result["data"]["keys"]) == 1
    assert result["data"]["keys"][0]["lockMac"] == sample_virtual_key.lockMac


async def test_step_user_success_sets_unique_id(
    hass,
    enable_custom_integrations,
    sample_virtual_key,
) -> None:
    with _patch_client(list_keys=[sample_virtual_key]):
        flow = await _start_user_flow(hass)
        await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=USER_INPUT
        )
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.unique_id == "user_example_com"


async def test_step_user_duplicate_aborts(
    hass,
    enable_custom_integrations,
    sample_virtual_key,
) -> None:
    with _patch_client(list_keys=[sample_virtual_key]):
        flow1 = await _start_user_flow(hass)
        await hass.config_entries.flow.async_configure(
            flow1["flow_id"], user_input=USER_INPUT
        )
        flow2 = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow2["flow_id"], user_input=USER_INPUT
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_key_sync_failure_reshows_the_form(
    hass,
    enable_custom_integrations,
) -> None:
    """A blip after the credentials were accepted must not crash the flow."""
    with patch("custom_components.ttlock_ble.config_flow.TtlockBleApiClient") as cls:
        instance = MagicMock()
        instance.async_login = AsyncMock(return_value=None)
        instance.async_list_keys = AsyncMock(
            side_effect=TtlockBleApiClientCommunicationError("down"),
        )
        cls.return_value = instance
        flow = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=USER_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "connection"}
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_key_sync_failure_after_verification_reshows_the_code_form(
    hass,
    enable_custom_integrations,
) -> None:
    """The same applies to the leg that already consumed a verification code."""
    with patch("custom_components.ttlock_ble.config_flow.TtlockBleApiClient") as cls:
        instance = MagicMock()
        # Only the first login trips 2FA; the one inside the key sync succeeds.
        instance.async_login = AsyncMock(
            side_effect=[TtlockBleApiClientVerificationRequiredError("2fa"), None],
        )
        instance.async_request_verification_code = AsyncMock(return_value=None)
        instance.async_validate_new_device_and_login = AsyncMock(return_value=None)
        instance.async_list_keys = AsyncMock(
            side_effect=TtlockBleApiClientCommunicationError("down"),
        )
        cls.return_value = instance
        flow = await _start_user_flow(hass)
        await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=USER_INPUT
        )
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=CODE_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "verify_code"
    assert result["errors"] == {"base": "connection"}


async def test_reauth_rejects_a_different_account(
    hass,
    enable_custom_integrations,
    sample_virtual_key,
) -> None:
    """Credentials for another account are not a re-authentication."""
    entry = _existing_entry(hass)
    with _patch_client(list_keys=[sample_virtual_key]):
        flow = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"],
            user_input={"username": "someone.else@example.com", "password": "pass"},
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert entry.data["username"] == "user@example.com"


async def test_reconfigure_rejects_a_different_account(
    hass,
    enable_custom_integrations,
    sample_virtual_key,
) -> None:
    """The same guard applies when editing credentials from the three-dot menu."""
    entry = _existing_entry(hass)
    with _patch_client(list_keys=[sample_virtual_key]):
        flow = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"],
            user_input={"username": "someone.else@example.com", "password": "pass"},
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "wrong_account"


async def test_step_cloud_aborts_when_a_lock_is_already_configured(
    hass,
    enable_custom_integrations,
    sample_virtual_key,
    sample_stored_key,
) -> None:
    """A lock added by hand blocks the cloud account that also holds it."""
    manual = MockConfigEntry(
        domain=DOMAIN,
        data={"keys": [sample_stored_key]},
        unique_id="e9:ef:a0:bd:22:1d",
    )
    manual.add_to_hass(hass)
    with _patch_client(list_keys=[sample_virtual_key]):
        flow = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=USER_INPUT
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_ignores_the_entry_being_reconfigured(
    hass,
    enable_custom_integrations,
    sample_virtual_key,
    sample_stored_key,
) -> None:
    """The collision check must not trip over the entry's own locks."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "user@example.com", "password": "pass", "keys": []},
        unique_id="user_example_com",
    )
    entry.add_to_hass(hass)
    with _patch_client(list_keys=[sample_virtual_key]):
        flow = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=NEW_INPUT
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["keys"][0]["lockMac"] == sample_virtual_key.lockMac


async def test_step_user_auth_error_shows_auth(
    hass, enable_custom_integrations
) -> None:
    with _patch_client(login_side_effect=TtlockBleApiClientAuthenticationError("bad")):
        flow = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=USER_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "auth"}


async def test_step_user_communication_error_shows_connection(
    hass,
    enable_custom_integrations,
) -> None:
    with _patch_client(login_side_effect=TtlockBleApiClientCommunicationError("down")):
        flow = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=USER_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "connection"}


async def test_step_user_generic_error_shows_unknown(
    hass,
    enable_custom_integrations,
) -> None:
    with _patch_client(login_side_effect=TtlockBleApiClientError("oops")):
        flow = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=USER_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


# --- Verification (2FA) ----------------------------------------------------


async def test_step_user_verification_required_transitions_to_code_step(
    hass,
    enable_custom_integrations,
) -> None:
    with _patch_client(
        login_side_effect=TtlockBleApiClientVerificationRequiredError("new device"),
    ) as instance:
        flow = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=USER_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "verify_code"
    instance.async_request_verification_code.assert_awaited_once_with(
        USER_INPUT["username"],
    )


async def test_step_user_verification_request_code_communication_error(
    hass,
    enable_custom_integrations,
) -> None:
    with _patch_client(
        login_side_effect=TtlockBleApiClientVerificationRequiredError("new device"),
        request_code_side_effect=TtlockBleApiClientCommunicationError("offline"),
    ):
        flow = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=USER_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "cloud"
    assert result["errors"] == {"base": "connection"}


async def test_step_user_verification_request_code_unknown_error(
    hass,
    enable_custom_integrations,
) -> None:
    with _patch_client(
        login_side_effect=TtlockBleApiClientVerificationRequiredError("new device"),
        request_code_side_effect=TtlockBleApiClientError("nope"),
    ):
        flow = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=USER_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "cloud"
    assert result["errors"] == {"base": "unknown"}


async def test_step_verify_code_success_creates_entry(
    hass,
    enable_custom_integrations,
    sample_virtual_key,
) -> None:
    with _patch_client(
        list_keys=[sample_virtual_key],
        login_side_effect=TtlockBleApiClientVerificationRequiredError("new device"),
    ):
        flow = await _start_user_flow(hass)
        await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=USER_INPUT
        )

    with _patch_client(list_keys=[sample_virtual_key]):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=CODE_INPUT
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["keys"][0]["lockMac"] == sample_virtual_key.lockMac


async def test_step_verify_code_invalid_shows_form(
    hass,
    enable_custom_integrations,
) -> None:
    with _patch_client(
        login_side_effect=TtlockBleApiClientVerificationRequiredError("new device"),
    ):
        flow = await _start_user_flow(hass)
        await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=USER_INPUT
        )

    with _patch_client(
        validate_side_effect=TtlockBleApiClientAuthenticationError("bad code"),
    ):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=CODE_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "verify_code"
    assert result["errors"] == {"base": "invalid_code"}


async def test_step_verify_code_communication_error(
    hass,
    enable_custom_integrations,
) -> None:
    with _patch_client(
        login_side_effect=TtlockBleApiClientVerificationRequiredError("new device"),
    ):
        flow = await _start_user_flow(hass)
        await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=USER_INPUT
        )

    with _patch_client(
        validate_side_effect=TtlockBleApiClientCommunicationError("offline"),
    ):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=CODE_INPUT
        )

    assert result["errors"] == {"base": "connection"}


async def test_step_verify_code_unknown_error(
    hass,
    enable_custom_integrations,
) -> None:
    with _patch_client(
        login_side_effect=TtlockBleApiClientVerificationRequiredError("new device"),
    ):
        flow = await _start_user_flow(hass)
        await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=USER_INPUT
        )

    with _patch_client(validate_side_effect=TtlockBleApiClientError("boom")):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=CODE_INPUT
        )

    assert result["errors"] == {"base": "unknown"}


async def test_step_verify_code_first_render_is_form(
    hass,
    enable_custom_integrations,
) -> None:
    with _patch_client(
        login_side_effect=TtlockBleApiClientVerificationRequiredError("new device"),
    ):
        flow = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=USER_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "verify_code"
    assert result.get("errors") in (None, {})


# --- Reauth ---------------------------------------------------------------


async def test_reauth_shows_confirm_form(hass, enable_custom_integrations) -> None:
    entry = _existing_entry(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"


async def test_reauth_success_updates_entry(
    hass,
    enable_custom_integrations,
    sample_virtual_key,
) -> None:
    entry = _existing_entry(hass)
    with _patch_client(list_keys=[sample_virtual_key]):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=NEW_INPUT
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "newpass"
    assert entry.data["keys"][0]["lockMac"] == sample_virtual_key.lockMac


async def test_reauth_auth_error_shows_auth(hass, enable_custom_integrations) -> None:
    entry = _existing_entry(hass)
    with _patch_client(login_side_effect=TtlockBleApiClientAuthenticationError("nope")):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=NEW_INPUT
        )
    assert result["errors"] == {"base": "auth"}


async def test_reauth_communication_error_shows_connection(
    hass,
    enable_custom_integrations,
) -> None:
    entry = _existing_entry(hass)
    with _patch_client(
        login_side_effect=TtlockBleApiClientCommunicationError("offline")
    ):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=NEW_INPUT
        )
    assert result["errors"] == {"base": "connection"}


async def test_reauth_unknown_error_shows_unknown(
    hass,
    enable_custom_integrations,
) -> None:
    entry = _existing_entry(hass)
    with _patch_client(login_side_effect=TtlockBleApiClientError("boom")):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=NEW_INPUT
        )
    assert result["errors"] == {"base": "unknown"}


async def test_reauth_verification_required_does_not_transition(
    hass,
    enable_custom_integrations,
) -> None:
    entry = _existing_entry(hass)
    with _patch_client(
        login_side_effect=TtlockBleApiClientVerificationRequiredError("new dev"),
    ):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=NEW_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "verification_required"}


# --- Reconfigure ----------------------------------------------------------


async def test_reconfigure_shows_form(hass, enable_custom_integrations) -> None:
    entry = _existing_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"


async def test_reconfigure_success_updates_entry(
    hass,
    enable_custom_integrations,
    sample_virtual_key,
) -> None:
    entry = _existing_entry(hass)
    with _patch_client(list_keys=[sample_virtual_key]):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=NEW_INPUT
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["password"] == "newpass"


async def test_reconfigure_communication_error(
    hass,
    enable_custom_integrations,
) -> None:
    entry = _existing_entry(hass)
    with _patch_client(
        login_side_effect=TtlockBleApiClientCommunicationError("offline")
    ):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=NEW_INPUT
        )
    assert result["errors"] == {"base": "connection"}


async def test_reconfigure_auth_error(hass, enable_custom_integrations) -> None:
    entry = _existing_entry(hass)
    with _patch_client(login_side_effect=TtlockBleApiClientAuthenticationError("nope")):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=NEW_INPUT
        )
    assert result["errors"] == {"base": "auth"}


async def test_reconfigure_unknown_error(hass, enable_custom_integrations) -> None:
    entry = _existing_entry(hass)
    with _patch_client(login_side_effect=TtlockBleApiClientError("boom")):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=NEW_INPUT
        )
    assert result["errors"] == {"base": "unknown"}


@pytest.mark.parametrize(
    ("side_effect", "expected"),
    [
        (TtlockBleApiClientAuthenticationError("nope"), "auth"),
        (TtlockBleApiClientError("something else"), "unknown"),
    ],
)
async def test_key_sync_failures_map_to_their_error_keys(
    hass,
    enable_custom_integrations,
    side_effect,
    expected,
) -> None:
    """Each cloud failure during the key sync gets its own form error."""
    with patch("custom_components.ttlock_ble.config_flow.TtlockBleApiClient") as cls:
        instance = MagicMock()
        instance.async_login = AsyncMock(return_value=None)
        instance.async_list_keys = AsyncMock(side_effect=side_effect)
        cls.return_value = instance
        flow = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=USER_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": expected}


async def test_reauth_key_sync_failure_reshows_the_form(
    hass,
    enable_custom_integrations,
) -> None:
    """The reauth leg re-shows its form too, instead of aborting the flow."""
    entry = _existing_entry(hass)
    with patch("custom_components.ttlock_ble.config_flow.TtlockBleApiClient") as cls:
        instance = MagicMock()
        instance.async_login = AsyncMock(return_value=None)
        instance.async_list_keys = AsyncMock(
            side_effect=TtlockBleApiClientCommunicationError("down"),
        )
        cls.return_value = instance
        flow = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input=NEW_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "connection"}
    assert entry.data["password"] == "pass"
