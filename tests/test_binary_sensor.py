from __future__ import annotations

import pytest
from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.ttlock_ble.connection import connection_signal, log_signal


async def test_connection_binary_sensor_created_for_each_key(
    hass,
    setup_integration,
) -> None:
    assert len(hass.states.async_all("binary_sensor")) == 2


async def test_connection_binary_sensor_reflects_initial_state(
    hass,
    setup_integration,
) -> None:
    state = hass.states.async_all("binary_sensor")[0]
    assert state.state == "on"


async def test_connection_binary_sensor_device_class(
    hass,
    setup_integration,
) -> None:
    state = hass.states.async_all("binary_sensor")[0]
    assert state.attributes["device_class"] == "connectivity"


async def test_connection_binary_sensor_has_unique_id(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    from homeassistant.helpers import entity_registry as er

    state = hass.states.async_all("binary_sensor")[0]
    registry = er.async_get(hass)
    entry = registry.async_get(state.entity_id)
    assert entry is not None
    assert entry.unique_id == f"{sample_virtual_key.lockMac}_connection"


async def test_connection_binary_sensor_is_diagnostic(
    hass,
    setup_integration,
) -> None:
    from homeassistant.helpers import entity_registry as er

    state = hass.states.async_all("binary_sensor")[0]
    registry = er.async_get(hass)
    entry = registry.async_get(state.entity_id)
    assert entry is not None
    assert entry.entity_category == er.EntityCategory.DIAGNOSTIC


async def test_connection_binary_sensor_icon_reflects_state(
    hass,
    setup_integration,
    sample_virtual_key,
    mock_ttlock_connection,
) -> None:
    """Icon switches between bluetooth-connect and bluetooth-off."""
    state = hass.states.async_all("binary_sensor")[0]
    assert state.attributes["icon"] == "mdi:bluetooth-connect"
    mock_ttlock_connection.is_connected = False
    async_dispatcher_send(
        hass,
        connection_signal(sample_virtual_key.lockMac),
        False,  # noqa: FBT003
    )
    await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).attributes["icon"] == "mdi:bluetooth-off"


async def test_connection_binary_sensor_updates_on_signal(
    hass,
    setup_integration,
    sample_virtual_key,
    mock_ttlock_connection,
) -> None:
    """A dispatcher signal pushes the freshest connection state without polling."""
    state = hass.states.async_all("binary_sensor")[0]
    assert state.state == "on"
    mock_ttlock_connection.is_connected = False
    async_dispatcher_send(
        hass,
        connection_signal(sample_virtual_key.lockMac),
        False,  # noqa: FBT003
    )
    await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == "off"


def _door_record(record_type: int, record_number: int = 1):
    from ttlock_ble import LogEntry

    return LogEntry(
        record_number=record_number,
        record_type=record_type,
        operate_date=None,
        lock_battery=80,
        accessory_battery=90,
    )


def _door_entity_id(hass, lock_mac: str) -> str | None:
    from homeassistant.helpers import entity_registry as er

    return er.async_get(hass).async_get_entity_id(
        "binary_sensor",
        "ttlock_ble",
        f"{lock_mac}_door",
    )


async def test_door_binary_sensor_absent_until_the_lock_reports_a_door(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    from ttlock_ble import LogOperate

    async_dispatcher_send(
        hass,
        log_signal(sample_virtual_key.lockMac),
        _door_record(int(LogOperate.MOBILE_UNLOCK)),
    )
    await hass.async_block_till_done()
    assert _door_entity_id(hass, sample_virtual_key.lockMac) is None
    assert len(hass.states.async_all("binary_sensor")) == 2


@pytest.mark.parametrize(
    ("record_type", "expected"),
    [
        (30, "off"),
        (31, "on"),
        (64, "on"),
    ],
    ids=["door_sensor_lock", "door_sensor_unlock", "door_not_close_alarm"],
)
async def test_door_binary_sensor_created_from_the_first_door_record(
    hass,
    setup_integration,
    sample_virtual_key,
    record_type: int,
    expected: str,
) -> None:
    async_dispatcher_send(
        hass,
        log_signal(sample_virtual_key.lockMac),
        _door_record(record_type),
    )
    await hass.async_block_till_done()
    entity_id = _door_entity_id(hass, sample_virtual_key.lockMac)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == expected
    assert state.attributes["device_class"] == "door"


async def test_door_binary_sensor_keeps_the_last_record_of_a_batch(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    from ttlock_ble import LogOperate

    signal = log_signal(sample_virtual_key.lockMac)
    async_dispatcher_send(
        hass, signal, _door_record(int(LogOperate.DOOR_SENSOR_UNLOCK))
    )
    async_dispatcher_send(hass, signal, _door_record(int(LogOperate.DOOR_SENSOR_LOCK)))
    await hass.async_block_till_done()
    entity_id = _door_entity_id(hass, sample_virtual_key.lockMac)
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "off"


async def test_door_binary_sensor_follows_later_records(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    from ttlock_ble import LogOperate

    signal = log_signal(sample_virtual_key.lockMac)
    async_dispatcher_send(hass, signal, _door_record(int(LogOperate.DOOR_SENSOR_LOCK)))
    await hass.async_block_till_done()
    async_dispatcher_send(
        hass, signal, _door_record(int(LogOperate.DOOR_SENSOR_UNLOCK))
    )
    await hass.async_block_till_done()
    entity_id = _door_entity_id(hass, sample_virtual_key.lockMac)
    assert hass.states.get(entity_id).state == "on"


async def test_door_binary_sensor_survives_a_reload_with_its_last_state(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    from ttlock_ble import LogOperate

    async_dispatcher_send(
        hass,
        log_signal(sample_virtual_key.lockMac),
        _door_record(int(LogOperate.DOOR_SENSOR_UNLOCK)),
    )
    await hass.async_block_till_done()
    entity_id = _door_entity_id(hass, sample_virtual_key.lockMac)
    assert await hass.config_entries.async_reload(setup_integration.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "on"
    async_dispatcher_send(
        hass,
        log_signal(sample_virtual_key.lockMac),
        _door_record(int(LogOperate.DOOR_SENSOR_LOCK), record_number=2),
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "off"


async def test_door_binary_sensor_registered_without_a_state_starts_unknown(
    hass,
    enable_bluetooth,
    enable_custom_integrations,
    sample_stored_key,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain="ttlock_ble",
        data={
            "username": "user@example.com",
            "password": "pass",
            "keys": [sample_stored_key],
        },
        unique_id="user_example_com",
    )
    entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        "binary_sensor",
        "ttlock_ble",
        f"{sample_stored_key['lockMac']}_door",
        config_entry=entry,
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = _door_entity_id(hass, sample_stored_key["lockMac"])
    assert hass.states.get(entity_id).state == "unknown"


async def test_door_binary_sensor_removed_entity_ignores_later_records(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    from homeassistant.helpers import entity_registry as er
    from ttlock_ble import LogOperate

    signal = log_signal(sample_virtual_key.lockMac)
    async_dispatcher_send(hass, signal, _door_record(int(LogOperate.DOOR_SENSOR_LOCK)))
    await hass.async_block_till_done()
    entity_id = _door_entity_id(hass, sample_virtual_key.lockMac)
    er.async_get(hass).async_remove(entity_id)
    await hass.async_block_till_done()
    async_dispatcher_send(
        hass, signal, _door_record(int(LogOperate.DOOR_SENSOR_UNLOCK))
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id) is None


def _passage_state(hass):
    return next(
        state
        for state in hass.states.async_all("binary_sensor")
        if state.entity_id.endswith("passage_mode_active")
    )


def _slot_22_to_23():
    from ttlock_ble import PassageModeSlot

    return PassageModeSlot(kind=1, day=6, month=0, start_minute=1320, end_minute=1380)


async def _note_slots(hass, entry, mac, slots) -> None:
    entry.runtime_data.coordinator.async_note_passage_slots(mac, slots)
    await hass.async_block_till_done()


async def test_passage_mode_is_unknown_until_the_lock_lists_its_slots(
    hass,
    setup_integration,
) -> None:
    state = _passage_state(hass)
    assert state.state == "unknown"
    assert state.attributes["slots"] == []


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        ("2026-11-14 22:30:00", "on"),
        ("2026-11-14 23:00:00", "off"),
        ("2026-11-15 22:30:00", "off"),
    ],
)
async def test_passage_mode_follows_the_slots_and_the_clock(
    hass,
    setup_integration,
    sample_virtual_key,
    freezer,
    moment,
    expected,
) -> None:
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to(f"{moment}+00:00")
    await _note_slots(
        hass, setup_integration, sample_virtual_key.lockMac, [_slot_22_to_23()]
    )

    state = _passage_state(hass)
    assert state.state == expected
    assert state.attributes["slots"] == [
        {"kind": 1, "day": 6, "month": 0, "start": "22:00", "end": "23:00"}
    ]


async def test_passage_mode_changes_at_the_moment_a_slot_starts_and_ends(
    hass,
    setup_integration,
    sample_virtual_key,
    freezer,
) -> None:
    """Nothing announces a slot starting or ending, so a timer is armed for it."""
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-11-14 21:59:30+00:00")
    await _note_slots(
        hass, setup_integration, sample_virtual_key.lockMac, [_slot_22_to_23()]
    )
    assert _passage_state(hass).state == "off"

    for moment, expected in (
        ("2026-11-14 22:00:00+00:00", "on"),
        ("2026-11-14 23:00:00+00:00", "off"),
    ):
        freezer.move_to(moment)
        async_fire_time_changed(hass, dt_util.parse_datetime(moment))
        await hass.async_block_till_done()
        assert _passage_state(hass).state == expected


async def test_passage_mode_writes_no_state_between_transitions(
    hass,
    setup_integration,
    sample_virtual_key,
    freezer,
) -> None:
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-11-14 12:00:00+00:00")
    await _note_slots(
        hass, setup_integration, sample_virtual_key.lockMac, [_slot_22_to_23()]
    )
    before = _passage_state(hass)

    for _minute in range(30):
        moment = dt_util.utcnow() + timedelta(minutes=1)
        freezer.move_to(moment)
        async_fire_time_changed(hass, moment)
        await hass.async_block_till_done()

    assert _passage_state(hass).last_reported == before.last_reported


async def test_passage_mode_has_no_timer_without_slots(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    await _note_slots(hass, setup_integration, sample_virtual_key.lockMac, [])
    assert _passage_state(hass).state == "off"


@pytest.mark.parametrize(
    ("restored", "expected"),
    [
        ([{"kind": 1, "day": 6, "month": 0, "start": "22:00", "end": "23:00"}], 1),
        ("not a list", 0),
        ([{"kind": 1}], 0),
    ],
)
async def test_passage_mode_restores_the_slots_it_last_showed(
    hass,
    enable_bluetooth,
    enable_custom_integrations,
    sample_stored_key,
    mock_cloud,
    mock_ttlock_connection,
    restored,
    expected,
) -> None:
    from homeassistant.core import State
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        mock_restore_cache,
    )

    from custom_components.ttlock_ble.const import DOMAIN

    mock_restore_cache(
        hass,
        [
            State(
                "binary_sensor.front_door_passage_mode_active",
                "off",
                {"slots": restored},
            )
        ],
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "u", "password": "p", "keys": [sample_stored_key]},
        unique_id="u",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert len(_passage_state(hass).attributes["slots"]) == expected
