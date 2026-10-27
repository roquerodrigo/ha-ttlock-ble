from __future__ import annotations

import pytest
from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.ttlock_ble.connection import connection_signal, log_signal


async def test_connection_binary_sensor_created_for_each_key(
    hass,
    setup_integration,
) -> None:
    assert len(hass.states.async_all("binary_sensor")) == 1


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
    assert len(hass.states.async_all("binary_sensor")) == 1


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
