"""Coverage for the manual key route: validation, build, and the config flow steps."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ttlock_ble.const import DOMAIN

MAC = "AA:BB:CC:DD:EE:FF"
AES_KEY_HEX = "0123456789abcdef0123456789abcdef"
MANUAL_INPUT = {
    "lock_mac": MAC,
    "aes_key": AES_KEY_HEX,
    "unlock_key": "123456",
    "admin_passcode": "999999",
    "lock_name": "Front door",
    "protocol_type": 5,
    "protocol_version": 3,
    "scene": 2,
    "group_id": 1,
    "org_id": 1,
}


@pytest.fixture(autouse=True)
def _lock_out_of_range():
    """Default every test to a lock nobody has seen, unless it says otherwise.

    Reaching the real bluetooth manager is what the cross-check does in
    production; here it only couples the validation tests to a stack they
    are not testing.
    """
    with patch(
        "custom_components.ttlock_ble.manual_key.async_last_service_info",
        return_value=None,
    ):
        yield


def _manual_key(hass):
    from custom_components.ttlock_ble.manual_key import TtlockBleManualKey

    return TtlockBleManualKey(hass)


def _advertisement_service_info(scene: int = 2) -> MagicMock:
    payload = bytes([scene, 0x00, 70, 0, 0, 0, 0]) + bytes.fromhex("ffeeddccbbaa")
    info = MagicMock()
    info.manufacturer_data = {0x0305: payload}
    return info


async def _start_manual_flow(hass):
    menu = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        menu["flow_id"], user_input={"next_step_id": "manual"}
    )


class TestValidation:
    async def test_accepts_a_well_formed_key(self, hass) -> None:
        assert _manual_key(hass).async_validate(dict(MANUAL_INPUT)) == {}

    @pytest.mark.parametrize(
        "mac",
        ["not-a-mac", "AA:BB:CC:DD:EE", "AABBCCDDEEFF", ""],
    )
    async def test_rejects_a_malformed_mac(self, hass, mac) -> None:
        errors = _manual_key(hass).async_validate({**MANUAL_INPUT, "lock_mac": mac})
        assert errors["lock_mac"] == "invalid_mac"

    @pytest.mark.parametrize(
        "aes_key",
        ["", "0123", "zz23456789abcdef0123456789abcdef", AES_KEY_HEX + "00"],
    )
    async def test_rejects_a_malformed_aes_key(self, hass, aes_key) -> None:
        errors = _manual_key(hass).async_validate({**MANUAL_INPUT, "aes_key": aes_key})
        assert errors["aes_key"] == "invalid_aes_key"

    async def test_accepts_a_separated_aes_key(self, hass) -> None:
        separated = ",".join(AES_KEY_HEX[i : i + 2] for i in range(0, 32, 2))
        assert (
            _manual_key(hass).async_validate(
                {**MANUAL_INPUT, "aes_key": separated},
            )
            == {}
        )

    async def test_rejects_a_non_numeric_unlock_key(self, hass) -> None:
        errors = _manual_key(hass).async_validate(
            {**MANUAL_INPUT, "unlock_key": "abc"},
        )
        assert errors["unlock_key"] == "invalid_unlock_key"

    async def test_rejects_a_non_numeric_admin_passcode(self, hass) -> None:
        errors = _manual_key(hass).async_validate(
            {**MANUAL_INPUT, "admin_passcode": "let me in"},
        )
        assert errors["admin_passcode"] == "invalid_admin_passcode"

    async def test_admin_passcode_is_optional(self, hass) -> None:
        assert (
            _manual_key(hass).async_validate(
                {**MANUAL_INPUT, "admin_passcode": ""},
            )
            == {}
        )


class TestAdvertisementCrossCheck:
    async def test_matching_advertisement_passes(self, hass) -> None:
        with patch(
            "custom_components.ttlock_ble.manual_key.async_last_service_info",
            return_value=_advertisement_service_info(scene=2),
        ):
            assert _manual_key(hass).async_validate(dict(MANUAL_INPUT)) == {}

    async def test_disagreeing_advertisement_is_rejected(self, hass) -> None:
        """The lock broadcasts its own frame header, so a wrong scene is catchable."""
        with patch(
            "custom_components.ttlock_ble.manual_key.async_last_service_info",
            return_value=_advertisement_service_info(scene=4),
        ):
            errors = _manual_key(hass).async_validate(dict(MANUAL_INPUT))
        assert errors["base"] == "protocol_mismatch"

    async def test_out_of_range_lock_is_not_an_error(self, hass) -> None:
        with patch(
            "custom_components.ttlock_ble.manual_key.async_last_service_info",
            return_value=None,
        ):
            assert _manual_key(hass).async_validate(dict(MANUAL_INPUT)) == {}

    async def test_foreign_manufacturer_data_is_not_an_error(self, hass) -> None:
        info = MagicMock()
        info.manufacturer_data = {0x004C: b"\x02\x15"}
        with patch(
            "custom_components.ttlock_ble.manual_key.async_last_service_info",
            return_value=info,
        ):
            assert _manual_key(hass).async_validate(dict(MANUAL_INPUT)) == {}


class TestBuild:
    async def test_maps_the_form_onto_a_virtual_key(self, hass) -> None:
        key = _manual_key(hass).build(dict(MANUAL_INPUT))
        assert key.lockMac == MAC
        assert key.aesKeyStr == AES_KEY_HEX
        assert key.unlockKey == "123456"
        assert key.adminPs == "999999"
        assert key.lockAlias == "Front door"
        assert key.lockVersion.protocolType == 5
        assert key.lockVersion.protocolVersion == 3
        assert key.lockVersion.scene == 2
        assert key.lockVersion.groupId == 1
        assert key.lockVersion.orgId == 1

    async def test_normalises_a_separated_aes_key(self, hass) -> None:
        """A key the BLE layer could not parse would only fail on connect."""
        separated = " ".join(AES_KEY_HEX[i : i + 2] for i in range(0, 32, 2))
        key = _manual_key(hass).build({**MANUAL_INPUT, "aes_key": separated})
        assert key.aesKeyStr == AES_KEY_HEX

    async def test_stored_key_round_trips_through_the_form(self, hass) -> None:
        from custom_components.ttlock_ble.manual_key import TtlockBleManualKey

        key = _manual_key(hass).build(dict(MANUAL_INPUT))
        defaults = TtlockBleManualKey.defaults_from(key.to_dict())
        rebuilt = _manual_key(hass).build(defaults)
        assert rebuilt.to_dict() == key.to_dict()

    async def test_names_itself_after_the_mac_when_unnamed(self, hass) -> None:
        key = _manual_key(hass).build({**MANUAL_INPUT, "lock_name": ""})
        assert key.lockAlias == f"TTLock {MAC}"

    async def test_lowercase_and_dashed_mac_is_normalised(self, hass) -> None:
        key = _manual_key(hass).build(
            {**MANUAL_INPUT, "lock_mac": "aa-bb-cc-dd-ee-ff"},
        )
        assert key.lockMac == MAC

    async def test_build_refuses_input_validation_would_reject(self, hass) -> None:
        with pytest.raises(ValueError, match="async_validate"):
            _manual_key(hass).build({**MANUAL_INPUT, "aes_key": "nope"})


class TestConfigFlow:
    async def test_manual_step_shows_the_form(
        self,
        hass,
        enable_custom_integrations,
    ) -> None:
        result = await _start_manual_flow(hass)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "manual"

    async def test_manual_step_creates_an_entry_without_credentials(
        self,
        hass,
        enable_custom_integrations,
    ) -> None:
        flow = await _start_manual_flow(hass)
        with patch(
            "custom_components.ttlock_ble.manual_key.async_last_service_info",
            return_value=None,
        ):
            result = await hass.config_entries.flow.async_configure(
                flow["flow_id"], user_input=dict(MANUAL_INPUT)
            )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "Front door"
        assert "username" not in result["data"]
        assert "password" not in result["data"]
        assert result["data"]["keys"][0]["lockMac"] == MAC
        assert result["data"]["keys"][0]["aesKeyStr"] == AES_KEY_HEX

    async def test_manual_step_keeps_the_form_on_bad_input(
        self,
        hass,
        enable_custom_integrations,
    ) -> None:
        flow = await _start_manual_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input={**MANUAL_INPUT, "aes_key": "nope"}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["aes_key"] == "invalid_aes_key"

    async def test_manual_step_is_keyed_by_the_lock_mac(
        self,
        hass,
        enable_custom_integrations,
    ) -> None:
        flow = await _start_manual_flow(hass)
        with patch(
            "custom_components.ttlock_ble.manual_key.async_last_service_info",
            return_value=None,
        ):
            await hass.config_entries.flow.async_configure(
                flow["flow_id"], user_input=dict(MANUAL_INPUT)
            )
        entry = hass.config_entries.async_entries(DOMAIN)[0]
        assert entry.unique_id == MAC.lower()

    async def test_manual_step_rejects_a_second_entry_for_the_same_lock(
        self,
        hass,
        enable_custom_integrations,
    ) -> None:
        MockConfigEntry(
            domain=DOMAIN,
            data={"keys": []},
            unique_id=MAC.lower(),
        ).add_to_hass(hass)
        flow = await _start_manual_flow(hass)
        with patch(
            "custom_components.ttlock_ble.manual_key.async_last_service_info",
            return_value=None,
        ):
            result = await hass.config_entries.flow.async_configure(
                flow["flow_id"], user_input=dict(MANUAL_INPUT)
            )
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"


class TestReconfigure:
    async def test_manual_entry_reconfigures_through_the_key_form(
        self,
        hass,
        enable_custom_integrations,
        mock_ttlock_connection,
    ) -> None:
        """An entry with no account must not be sent to the credentials form."""
        key = _manual_key(hass).build(dict(MANUAL_INPUT))
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"keys": [key.to_dict()]},
            unique_id=MAC.lower(),
        )
        entry.add_to_hass(hass)
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reconfigure_manual"

    async def test_reconfigure_updates_the_stored_key(
        self,
        hass,
        enable_custom_integrations,
        mock_ttlock_connection,
    ) -> None:
        key = _manual_key(hass).build(dict(MANUAL_INPUT))
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"keys": [key.to_dict()]},
            unique_id=MAC.lower(),
        )
        entry.add_to_hass(hass)
        flow = await entry.start_reconfigure_flow(hass)
        with patch(
            "custom_components.ttlock_ble.manual_key.async_last_service_info",
            return_value=None,
        ):
            result = await hass.config_entries.flow.async_configure(
                flow["flow_id"],
                user_input={**MANUAL_INPUT, "unlock_key": "654321"},
            )
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"
        assert entry.data["keys"][0]["unlockKey"] == "654321"

    async def test_reconfigure_keeps_the_form_on_bad_input(
        self,
        hass,
        enable_custom_integrations,
        mock_ttlock_connection,
    ) -> None:
        key = _manual_key(hass).build(dict(MANUAL_INPUT))
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"keys": [key.to_dict()]},
            unique_id=MAC.lower(),
        )
        entry.add_to_hass(hass)
        flow = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"],
            user_input={**MANUAL_INPUT, "unlock_key": "nope"},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["unlock_key"] == "invalid_unlock_key"


async def test_manual_step_rejects_a_lock_a_cloud_entry_already_has(
    hass,
    enable_custom_integrations,
) -> None:
    """A cloud entry is keyed by the account, so the MAC has to be checked too."""
    key = _manual_key(hass).build(dict(MANUAL_INPUT))
    MockConfigEntry(
        domain=DOMAIN,
        data={"username": "user@example.com", "password": "p", "keys": [key.to_dict()]},
        unique_id="user_example_com",
    ).add_to_hass(hass)
    flow = await _start_manual_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], user_input=dict(MANUAL_INPUT)
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
