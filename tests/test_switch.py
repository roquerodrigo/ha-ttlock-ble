from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError
from ttlock_ble import TTLockError


def _switch_state(hass):
    return hass.states.async_all("switch")[0]


async def test_sound_switch_created_for_an_admin_key(hass, setup_integration) -> None:
    assert len(hass.states.async_all("switch")) == 1


async def test_sound_switch_starts_without_a_value(hass, setup_integration) -> None:
    """Nothing reads the setting back, so nothing is known until something sets it."""
    assert _switch_state(hass).state == "unknown"


async def test_sound_switch_is_assumed(hass, setup_integration) -> None:
    """The command can be sent; the answer cannot be read."""
    assert _switch_state(hass).attributes["assumed_state"] is True


async def test_sound_switch_has_unique_id(
    hass, setup_integration, sample_virtual_key
) -> None:
    from homeassistant.helpers import entity_registry as er

    entry = er.async_get(hass).async_get(_switch_state(hass).entity_id)
    assert entry is not None
    assert entry.unique_id == f"{sample_virtual_key.lockMac}_sound"


@pytest.mark.parametrize(
    ("service", "expected"),
    [("turn_on", True), ("turn_off", False)],
)
async def test_sound_switch_sends_the_command(
    hass,
    setup_integration,
    mock_ttlock_connection,
    service,
    expected,
) -> None:
    state = _switch_state(hass)
    await hass.services.async_call(
        "switch",
        service,
        {"entity_id": state.entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    mock_ttlock_connection.async_set_lock_sound.assert_awaited_with(enabled=expected)
    assert hass.states.get(state.entity_id).state == ("on" if expected else "off")


async def test_a_refused_command_surfaces_and_keeps_the_old_value(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    """A failed write must not leave the entity claiming it took effect."""
    state = _switch_state(hass)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": state.entity_id}, blocking=True
    )
    await hass.async_block_till_done()

    mock_ttlock_connection.async_set_lock_sound = AsyncMock(
        side_effect=TTLockError("lock refused"),
    )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": state.entity_id}, blocking=True
        )
    assert hass.states.get(state.entity_id).state == "on"


async def test_no_switch_without_the_admin_passcode(
    hass,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    """CHECK_ADMIN needs it; an entity that can only ever fail is worse than none."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    key = dict(sample_stored_key)
    key["adminPs"] = ""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "u", "password": "p", "keys": [key]},
        unique_id="u",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.async_all("switch") == []


async def test_no_switch_for_a_non_admin_key(
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
    assert hass.states.async_all("switch") == []
