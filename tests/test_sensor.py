from __future__ import annotations

from unittest.mock import AsyncMock


def _battery_state(hass):
    """The battery sensor, picked by device class so last-seen cannot shadow it."""
    return next(
        state
        for state in hass.states.async_all("sensor")
        if state.attributes.get("device_class") == "battery"
    )


def _last_seen_state(hass):
    """The last-seen sensor."""
    return next(
        state
        for state in hass.states.async_all("sensor")
        if state.attributes.get("device_class") == "timestamp"
    )


def _clock_drift_state(hass):
    """The clock-drift sensor."""
    return next(
        state
        for state in hass.states.async_all("sensor")
        if state.attributes.get("device_class") == "duration"
    )


async def test_clock_drift_is_unknown_until_a_session_carried_a_comparison(
    hass,
    setup_integration,
) -> None:
    """Nothing here connects for it, so before the first check there is no answer."""
    assert _clock_drift_state(hass).state == "unknown"


async def test_clock_drift_reports_the_last_comparison(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    from custom_components.ttlock_ble.clock_sync_store import async_get_clock_sync_store

    store = await async_get_clock_sync_store(hass)
    store.async_remember(
        sample_virtual_key.lockMac,
        {"checked_at": "2026-08-29T22:00:00+00:00", "drift_seconds": -12.5},
    )
    setup_integration.runtime_data.coordinator.async_update_listeners()
    await hass.async_block_till_done()

    state = _clock_drift_state(hass)
    assert float(state.state) == -12.5
    assert state.attributes["checked_at"] == "2026-08-29T22:00:00+00:00"


async def test_battery_sensor_created_for_each_key(hass, setup_integration) -> None:
    assert len(hass.states.async_all("sensor")) == 3


async def test_battery_sensor_reports_coordinator_value(
    hass,
    setup_integration,
) -> None:
    state = _battery_state(hass)
    assert state.state == "80"


async def test_battery_sensor_unit_and_device_class(
    hass,
    setup_integration,
) -> None:
    state = _battery_state(hass)
    assert state.attributes["unit_of_measurement"] == "%"
    assert state.attributes["device_class"] == "battery"
    assert state.attributes["state_class"] == "measurement"


async def test_battery_sensor_unknown_when_coordinator_returns_none(
    hass,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    mock_ttlock_connection.async_query_state = AsyncMock(return_value=None)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "username": "u",
            "password": "p",
            "keys": [sample_stored_key],
        },
        unique_id="u",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = _battery_state(hass)
    assert state.state in ("unknown", "unavailable")


async def test_battery_sensor_has_unique_id(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    from homeassistant.helpers import entity_registry as er

    state = _battery_state(hass)
    registry = er.async_get(hass)
    entry = registry.async_get(state.entity_id)
    assert entry is not None
    assert entry.unique_id == f"{sample_virtual_key.lockMac}_battery"


async def test_battery_sensor_updates_from_push_event(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    """A push event carrying `battery` updates the sensor without polling."""
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    from ttlock_ble import LockEvent

    from custom_components.ttlock_ble.connection import event_signal

    state = _battery_state(hass)
    assert state.state == "80"
    pushed = LockEvent.from_payload(0x14, 1, bytes.fromhex("2a0102"))  # battery=0x2a
    async_dispatcher_send(
        hass,
        event_signal(sample_virtual_key.lockMac),
        pushed,
    )
    await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == "42"


async def test_battery_sensor_ignores_push_event_without_battery(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    """An event with no decoded battery byte must not clobber the last value."""
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    from ttlock_ble import LockEvent

    from custom_components.ttlock_ble.connection import event_signal

    state = _battery_state(hass)
    assert state.state == "80"
    async_dispatcher_send(
        hass,
        event_signal(sample_virtual_key.lockMac),
        LockEvent(cmd_echo=0x47, status=1, data=b""),
    )
    await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == "80"


async def test_battery_sensor_is_diagnostic(
    hass,
    setup_integration,
) -> None:
    from homeassistant.helpers import entity_registry as er

    state = _battery_state(hass)
    registry = er.async_get(hass)
    entry = registry.async_get(state.entity_id)
    assert entry is not None
    assert entry.entity_category == er.EntityCategory.DIAGNOSTIC


def test_battery_sync_from_coordinator_no_snapshot_keeps_value(
    hass,
    sample_virtual_key,
) -> None:
    """An empty coordinator snapshot leaves `_attr_native_value` untouched."""

    from custom_components.ttlock_ble.clock_sync_store import TtlockBleClockSyncStore
    from custom_components.ttlock_ble.coordinator import TtlockBleDataUpdateCoordinator
    from custom_components.ttlock_ble.device_description_store import (
        TtlockBleDeviceDescriptionStore,
    )
    from custom_components.ttlock_ble.sensor import TtlockBleBatterySensor

    coordinator = TtlockBleDataUpdateCoordinator(
        hass,
        {},
        TtlockBleDeviceDescriptionStore(hass),
        TtlockBleClockSyncStore(hass),
    )
    coordinator.data = {}
    entity = TtlockBleBatterySensor(coordinator, sample_virtual_key)
    assert entity.native_value is None
    entity._attr_native_value = 64
    entity._sync_from_coordinator()
    assert entity.native_value == 64


async def test_last_seen_sensor_created_for_each_key(hass, setup_integration) -> None:
    assert _last_seen_state(hass) is not None


async def test_last_seen_sensor_has_unique_id(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    from homeassistant.helpers import entity_registry as er

    state = _last_seen_state(hass)
    entry = er.async_get(hass).async_get(state.entity_id)
    assert entry is not None
    assert entry.unique_id == f"{sample_virtual_key.lockMac}_last_seen"


async def test_last_seen_is_unknown_while_nothing_was_ever_received(
    hass,
    setup_integration,
) -> None:
    """No advertisement in the bluetooth manager's history means no answer to give."""
    assert _last_seen_state(hass).state in ("unknown", "unavailable")


def _added_last_seen_entity(hass):
    """The live last-seen entity, as the platform added it."""
    entity_id = _last_seen_state(hass).entity_id
    component = hass.data["entity_components"]["sensor"]
    return next(e for e in component.entities if e.entity_id == entity_id)


def _sensor(hass, setup_integration, sample_virtual_key):
    from custom_components.ttlock_ble.sensor import TtlockBleLastSeenSensor

    entity = TtlockBleLastSeenSensor(
        setup_integration.runtime_data.coordinator,
        sample_virtual_key,
    )
    entity.hass = hass
    return entity


async def test_last_seen_converts_the_monotonic_reception_time(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    """The manager stores a monotonic instant; the sensor reports wall-clock."""
    from unittest.mock import MagicMock, patch

    from homeassistant.util import dt as dt_util

    entity = _sensor(hass, setup_integration, sample_virtual_key)
    info = MagicMock()
    info.time = 1000.0
    with (
        patch(
            "custom_components.ttlock_ble.sensor.async_last_service_info",
            return_value=info,
        ),
        patch(
            "custom_components.ttlock_ble.sensor.MONOTONIC_TIME",
            return_value=1060.0,
        ),
    ):
        value = entity.native_value
    assert value is not None
    assert 55 <= (dt_util.utcnow() - value).total_seconds() <= 65


async def test_last_seen_is_stable_while_the_advertisement_does_not_change(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    """Recomputing on every poll would walk the timestamp and churn the state."""
    from unittest.mock import MagicMock, patch

    entity = _sensor(hass, setup_integration, sample_virtual_key)
    info = MagicMock()
    info.time = 1000.0
    with patch(
        "custom_components.ttlock_ble.sensor.async_last_service_info",
        return_value=info,
    ):
        with patch(
            "custom_components.ttlock_ble.sensor.MONOTONIC_TIME", return_value=1060.0
        ):
            first = entity.native_value
        with patch(
            "custom_components.ttlock_ble.sensor.MONOTONIC_TIME", return_value=1200.0
        ):
            second = entity.native_value
    assert first == second


async def test_last_seen_moves_on_a_newer_advertisement(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    from unittest.mock import MagicMock, patch

    entity = _sensor(hass, setup_integration, sample_virtual_key)
    older, newer = MagicMock(), MagicMock()
    older.time, newer.time = 1000.0, 1100.0
    with patch(
        "custom_components.ttlock_ble.sensor.MONOTONIC_TIME", return_value=1200.0
    ):
        with patch(
            "custom_components.ttlock_ble.sensor.async_last_service_info",
            return_value=older,
        ):
            first = entity.native_value
        with patch(
            "custom_components.ttlock_ble.sensor.async_last_service_info",
            return_value=newer,
        ):
            second = entity.native_value
    assert second > first


async def test_last_seen_keeps_its_value_when_history_is_dropped(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    """Losing the cached advertisement is not evidence the lock went away."""
    from unittest.mock import MagicMock, patch

    entity = _sensor(hass, setup_integration, sample_virtual_key)
    info = MagicMock()
    info.time = 1000.0
    with (
        patch(
            "custom_components.ttlock_ble.sensor.async_last_service_info",
            return_value=info,
        ),
        patch(
            "custom_components.ttlock_ble.sensor.MONOTONIC_TIME", return_value=1060.0
        ),
    ):
        seen = entity.native_value
    with patch(
        "custom_components.ttlock_ble.sensor.async_last_service_info",
        return_value=None,
    ):
        assert entity.native_value == seen


def _added_last_seen_entity(hass):
    """The live last-seen entity, as the platform added it."""
    entity_id = _last_seen_state(hass).entity_id
    component = hass.data["entity_components"]["sensor"]
    return next(e for e in component.entities if e.entity_id == entity_id)


async def test_last_seen_never_polls_the_lock(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    """Reading local memory must not open a BLE session.

    `should_poll` on a `CoordinatorEntity` means `async_request_refresh`,
    which connects to the lock. This sensor keeps its own timer instead.
    """
    assert _sensor(hass, setup_integration, sample_virtual_key).should_poll is False


async def test_last_seen_rereads_without_touching_the_coordinator(
    hass,
    setup_integration,
) -> None:
    """Nothing announces an advertisement the manager recorded but did not dispatch."""
    from datetime import timedelta
    from unittest.mock import MagicMock, patch

    from homeassistant.util import dt as dt_util

    state = _last_seen_state(hass)
    info = MagicMock()
    info.time = 1000.0
    with (
        patch(
            "custom_components.ttlock_ble.sensor.async_last_service_info",
            return_value=info,
        ),
        patch(
            "custom_components.ttlock_ble.sensor.MONOTONIC_TIME", return_value=1010.0
        ),
        patch.object(
            setup_integration.runtime_data.coordinator,
            "async_request_refresh",
        ) as refresh,
    ):
        _added_last_seen_entity(hass)._async_reread_history(dt_util.utcnow())
        await hass.async_block_till_done()
        expected = dt_util.utcnow() - timedelta(seconds=10)

    written = dt_util.parse_datetime(hass.states.get(state.entity_id).state)
    assert written is not None
    assert abs((written - expected).total_seconds()) < 5
    refresh.assert_not_called()
