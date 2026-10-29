from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError
from ttlock_ble import FingerprintEntry

from custom_components.ttlock_ble.credential_type import TtlockBleCredentialType
from custom_components.ttlock_ble.data import TtlockBleKnownCredential


def _button_state(hass):
    return hass.states.async_all("button")[0]


async def test_refresh_button_created_for_an_admin_key(hass, setup_integration) -> None:
    assert len(hass.states.async_all("button")) == 1


async def test_no_refresh_button_for_a_non_admin_key(
    hass,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    key = dict(sample_stored_key)
    key["userType"] = "110302"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "u", "password": "p", "keys": [key]},
        unique_id="u",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.async_all("button") == []


async def test_refresh_button_has_unique_id(
    hass, setup_integration, sample_virtual_key
) -> None:
    from homeassistant.helpers import entity_registry as er

    entry = er.async_get(hass).async_get(_button_state(hass).entity_id)
    assert entry is not None
    assert entry.unique_id == f"{sample_virtual_key.lockMac}_refresh_credentials"


async def test_refresh_button_is_config_category(hass, setup_integration) -> None:
    from homeassistant.helpers import entity_registry as er

    entry = er.async_get(hass).async_get(_button_state(hass).entity_id)
    assert entry is not None
    assert entry.entity_category == er.EntityCategory.CONFIG


async def test_refresh_button_lives_on_the_lock_device(
    hass, setup_integration, sample_virtual_key
) -> None:
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.device_registry import format_mac

    from custom_components.ttlock_ble.const import DOMAIN

    lock_device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, format_mac(sample_virtual_key.lockMac)), setup_integration.entry_id
    )
    assert lock_device is not None

    button_entry = er.async_get(hass).async_get(_button_state(hass).entity_id)
    assert button_entry is not None
    assert button_entry.device_id == lock_device.id


async def test_refresh_button_press_forces_a_read_bypassing_the_pacing(
    hass,
    setup_integration,
    mock_ttlock_connection,
    sample_virtual_key,
) -> None:
    """Pressing must land even immediately after a read, when the interval says wait."""
    coordinator = setup_integration.runtime_data.coordinator
    mac = sample_virtual_key.lockMac
    coordinator._credentials_checked_at[mac] = coordinator.hass.loop.time()
    entries = [
        FingerprintEntry(
            fingerprint_id=bytes([0x00, 0x00, 0x00, 0x2A]),
            slot=1,
            start_date=None,
            end_date=None,
        )
    ]
    mock_ttlock_connection.async_get_fingerprints = AsyncMock(return_value=entries)
    mock_ttlock_connection.async_get_cards = AsyncMock(return_value=[])
    mock_ttlock_connection.async_get_passcodes = AsyncMock(return_value=[])

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": _button_state(hass).entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()

    mock_ttlock_connection.async_get_fingerprints.assert_awaited_once()
    assert coordinator.async_credentials(mac, TtlockBleCredentialType.FINGERPRINT) == [
        TtlockBleKnownCredential.from_fingerprint(entry) for entry in entries
    ]


async def test_refresh_button_still_respects_the_admin_gate(
    hass,
    setup_integration,
    mock_ttlock_connection,
    sample_virtual_key,
) -> None:
    """`force` bypasses the pacing interval, never the admin-password check."""
    sample_virtual_key.adminPs = ""

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": _button_state(hass).entity_id},
            blocking=True,
        )

    mock_ttlock_connection.async_get_fingerprints.assert_not_awaited()


async def test_refresh_button_press_fails_when_the_lock_is_not_reached(
    hass,
    setup_integration,
    mock_ttlock_connection,
    sample_virtual_key,
) -> None:
    mock_ttlock_connection.async_get_fingerprints = AsyncMock(return_value=None)

    with pytest.raises(HomeAssistantError) as error:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": _button_state(hass).entity_id},
            blocking=True,
        )

    assert error.value.translation_key == "credentials_not_read"
    assert error.value.translation_placeholders == {
        "lock": sample_virtual_key.lockAlias
    }
