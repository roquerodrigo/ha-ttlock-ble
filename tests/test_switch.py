from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError
from ttlock_ble import LockSound, TTLockError


def _switch_state(hass):
    return next(
        state
        for state in hass.states.async_all("switch")
        if state.entity_id.endswith("sound")
    )


async def test_sound_switch_created_for_an_admin_key(hass, setup_integration) -> None:
    assert len(hass.states.async_all("switch")) == 2


async def test_sound_switch_starts_without_a_value(hass, setup_integration) -> None:
    """Setup opens no session, and nothing connects just to learn the setting."""
    assert _switch_state(hass).state == "unknown"


async def test_sound_switch_is_not_assumed(hass, setup_integration) -> None:
    """The setting is read from the lock, so one toggle is the honest presentation."""
    assert "assumed_state" not in _switch_state(hass).attributes


@pytest.mark.parametrize("enabled", [True, False])
async def test_sound_switch_follows_what_the_lock_reports(
    hass,
    setup_integration,
    mock_ttlock_connection,
    enabled,
) -> None:
    mock_ttlock_connection.async_get_lock_sound.return_value = LockSound(
        enabled=enabled, volume=None
    )
    state = _switch_state(hass)

    await setup_integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(state.entity_id).state == ("on" if enabled else "off")


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


MAC = "AA:BB:CC:DD:EE:FF"


def _passage_switch(hass):
    return next(
        state
        for state in hass.states.async_all("switch")
        if state.entity_id.endswith("passage_mode")
    )


async def _turn(hass, service: str) -> None:
    await hass.services.async_call(
        "switch",
        service,
        {"entity_id": _passage_switch(hass).entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()


def _written_days(connection) -> list[int]:
    return [
        call.args[0].day for call in connection.async_add_passage_slot.await_args_list
    ]


async def test_passage_mode_switch_starts_off(hass, setup_integration) -> None:
    """Nothing has been written, and that is known without asking the lock."""
    assert _passage_switch(hass).state == "off"


async def test_the_passage_mode_switch_is_a_control_not_a_setting(
    hass, setup_integration
) -> None:
    from homeassistant.helpers import entity_registry as er

    entry = er.async_get(hass).async_get(_passage_switch(hass).entity_id)
    assert entry is not None
    assert entry.entity_category is None


async def test_turning_passage_mode_on_adds_a_slot_for_every_weekday(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    from custom_components.ttlock_ble.passage_mode import always_slots

    mock_ttlock_connection.async_get_passage_slots.return_value = always_slots()

    await _turn(hass, "turn_on")

    assert _written_days(mock_ttlock_connection) == [1, 2, 3, 4, 5, 6, 7]
    mock_ttlock_connection.async_clear_passage_slots.assert_not_awaited()
    mock_ttlock_connection.async_unlock.assert_not_awaited()
    assert _passage_switch(hass).state == "on"


async def test_turning_passage_mode_on_reads_the_slots_back(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    from custom_components.ttlock_ble.passage_mode import always_slots

    mock_ttlock_connection.async_get_passage_slots.return_value = always_slots()

    await _turn(hass, "turn_on")

    coordinator = setup_integration.runtime_data.coordinator
    assert coordinator.async_passage_slots(MAC) == always_slots()


async def test_turning_passage_mode_off_removes_only_what_the_switch_wrote(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    await _turn(hass, "turn_on")
    await _turn(hass, "turn_off")

    deleted = [
        call.args[0].day
        for call in mock_ttlock_connection.async_delete_passage_slot.await_args_list
    ]
    assert deleted == [1, 2, 3, 4, 5, 6, 7]
    mock_ttlock_connection.async_clear_passage_slots.assert_not_awaited()
    assert _passage_switch(hass).state == "off"


async def test_turning_passage_mode_off_leaves_a_schedule_somebody_else_set(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    await _turn(hass, "turn_off")

    mock_ttlock_connection.async_delete_passage_slot.assert_not_awaited()
    mock_ttlock_connection.async_clear_passage_slots.assert_not_awaited()


async def test_turning_passage_mode_on_twice_writes_each_slot_once(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    await _turn(hass, "turn_on")
    await _turn(hass, "turn_on")

    assert _written_days(mock_ttlock_connection) == [1, 2, 3, 4, 5, 6, 7]


async def test_the_switch_is_off_once_its_slots_are_gone_from_the_lock(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    """Somebody cleared the lock in the official app."""
    await _turn(hass, "turn_on")
    setup_integration.runtime_data.coordinator.async_note_passage_slots(MAC, [])
    await hass.async_block_till_done()

    assert _passage_switch(hass).state == "off"


async def test_a_refused_slot_rolls_back_what_was_written(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    from custom_components.ttlock_ble.switch_slot_store import (
        async_get_switch_slot_store,
    )

    mock_ttlock_connection.async_add_passage_slot.side_effect = [
        None,
        None,
        TTLockError("refused"),
    ]

    with pytest.raises(HomeAssistantError):
        await _turn(hass, "turn_on")

    deleted = [
        call.args[0].day
        for call in mock_ttlock_connection.async_delete_passage_slot.await_args_list
    ]
    assert deleted == [1, 2]
    assert (await async_get_switch_slot_store(hass)).get(MAC) == []
    assert _passage_switch(hass).state == "off"


async def test_a_failed_turn_off_keeps_what_is_left_to_remove(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    """The record shrinks with the lock, so a retry never asks for a gone slot."""
    from custom_components.ttlock_ble.switch_slot_store import (
        async_get_switch_slot_store,
    )

    await _turn(hass, "turn_on")
    mock_ttlock_connection.async_delete_passage_slot.side_effect = [
        None,
        None,
        TTLockError("out of range"),
    ]

    with pytest.raises(HomeAssistantError):
        await _turn(hass, "turn_off")

    assert [
        slot.day for slot in (await async_get_switch_slot_store(hass)).get(MAC)
    ] == [
        3,
        4,
        5,
        6,
        7,
    ]

    mock_ttlock_connection.async_delete_passage_slot.side_effect = None
    mock_ttlock_connection.async_delete_passage_slot.reset_mock()
    await _turn(hass, "turn_off")

    deleted = [
        call.args[0].day
        for call in mock_ttlock_connection.async_delete_passage_slot.await_args_list
    ]
    assert deleted == [3, 4, 5, 6, 7]


@pytest.mark.parametrize(
    "stored_key_update",
    [{"featureValue": "1"}, {"adminPs": ""}],
)
async def test_passage_mode_entities_need_an_admin_key_on_a_lock_with_the_feature(
    hass,
    enable_bluetooth,
    enable_custom_integrations,
    sample_stored_key,
    mock_cloud,
    mock_ttlock_connection,
    stored_key_update,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "username": "u",
            "password": "p",
            "keys": [{**sample_stored_key, **stored_key_update}],
        },
        unique_id="u",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert not [
        state
        for domain in ("switch", "binary_sensor", "sensor")
        for state in hass.states.async_all(domain)
        if "passage_mode" in state.entity_id
    ]
