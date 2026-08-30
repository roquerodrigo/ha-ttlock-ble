from __future__ import annotations

import datetime as dt
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.util import dt as dt_util
from ttlock_ble import DeviceInfo

from custom_components.ttlock_ble.clock_sync_store import TtlockBleClockSyncStore
from custom_components.ttlock_ble.coordinator import (
    CLOCK_CHECK_INTERVAL_SECONDS,
    CLOCK_DRIFT_THRESHOLD_SECONDS,
    TtlockBleDataUpdateCoordinator,
    _parse_lock_state,
)
from custom_components.ttlock_ble.device_description_store import (
    TtlockBleDeviceDescriptionStore,
)


def test_parse_lock_state_locked() -> None:
    assert _parse_lock_state(0) is True


def test_parse_lock_state_unlocked() -> None:
    assert _parse_lock_state(1) is False


@pytest.mark.parametrize("raw_state", [-1, 2, 9])
def test_parse_lock_state_unknown(raw_state: int) -> None:
    assert _parse_lock_state(raw_state) is None


def _mock_connection(*, query_return=(0, 80), mac="AA:BB:CC:DD:EE:FF") -> MagicMock:
    conn = MagicMock()
    conn.key = MagicMock(lockMac=mac)
    conn.async_query_state = AsyncMock(return_value=query_return)
    conn.async_get_operation_log = AsyncMock(return_value=[])
    conn.async_get_device_info = AsyncMock(return_value=None)
    conn.async_get_lock_time = AsyncMock(return_value=None)
    conn.async_calibrate_time = AsyncMock(return_value=True)
    return conn


def _coordinator(hass, connections, descriptions=None, clock_syncs=None):
    return TtlockBleDataUpdateCoordinator(
        hass=hass,
        connections=connections,
        descriptions=descriptions or TtlockBleDeviceDescriptionStore(hass),
        clock_syncs=clock_syncs or TtlockBleClockSyncStore(hass),
    )


async def test_poll_keeps_state_when_log_read_fails(hass) -> None:
    """The operation log only feeds the event entity; it must not void the state."""
    conn = _mock_connection(query_return=(0, 80))
    conn.async_get_operation_log = AsyncMock(side_effect=ValueError("garbled frame"))
    coordinator = _coordinator(hass, {"AA:BB:CC:DD:EE:FF": conn})
    data = await coordinator._async_update_data()
    assert data["AA:BB:CC:DD:EE:FF"] == {"locked": True, "battery_level": 80}


async def test_coordinator_exposes_connections(hass) -> None:
    connections = {"AA:BB:CC:DD:EE:FF": _mock_connection()}
    coordinator = _coordinator(hass, connections)
    assert coordinator.connections is connections


async def test_coordinator_polls_state_locked(hass, sample_virtual_key) -> None:
    conn = _mock_connection(query_return=(0, 75))
    coordinator = _coordinator(hass, {sample_virtual_key.lockMac: conn})
    data = await coordinator._async_update_data()
    state = data[sample_virtual_key.lockMac]
    assert state["locked"] is True
    assert state["battery_level"] == 75


async def test_coordinator_polls_state_unlocked(hass, sample_virtual_key) -> None:
    conn = _mock_connection(query_return=(1, 60))
    coordinator = _coordinator(hass, {sample_virtual_key.lockMac: conn})
    data = await coordinator._async_update_data()
    assert data[sample_virtual_key.lockMac]["locked"] is False


async def test_coordinator_blanks_the_readings_when_a_query_returns_none(
    hass,
    sample_virtual_key,
) -> None:
    conn = _mock_connection(query_return=None)
    coordinator = _coordinator(hass, {sample_virtual_key.lockMac: conn})
    data = await coordinator._async_update_data()
    state = data[sample_virtual_key.lockMac]
    assert state["locked"] is None
    assert state["battery_level"] is None


async def test_coordinator_polls_every_connection_once(
    hass, sample_virtual_key
) -> None:
    other_key = sample_virtual_key.lockMac.replace("AA", "11")
    conns = {
        sample_virtual_key.lockMac: _mock_connection(),
        other_key: _mock_connection(query_return=(1, 50)),
    }
    coordinator = _coordinator(hass, conns)
    data = await coordinator._async_update_data()
    assert set(data) == set(conns)
    for conn in conns.values():
        conn.async_query_state.assert_awaited_once()


def _advertisement(
    *,
    unlocked: bool,
    battery: int = 66,
    dormant: bool = False,
    records: bool = False,
):
    from ttlock_ble import LockAdvertisement, LockState

    if dormant:
        lock_state = None
    else:
        lock_state = LockState.UNLOCKED if unlocked else LockState.LOCKED
    return LockAdvertisement(
        protocol_type=5,
        protocol_version=3,
        scene=2,
        lock_state=lock_state,
        has_new_records=records,
        is_setting_mode=False,
        is_dormant=dormant,
        battery=battery,
        lock_mac="AA:BB:CC:DD:EE:FF",
    )


def _task_entry(hass) -> MagicMock:
    """A config entry whose `async_create_task` really schedules the coroutine."""
    entry = MagicMock()
    entry.async_create_task = lambda _hass, coro, name=None: hass.async_create_task(  # noqa: ARG005
        coro,
    )
    return entry


async def test_apply_advertisement_publishes_state_without_polling(
    hass,
    sample_virtual_key,
) -> None:
    conn = _mock_connection()
    coordinator = _coordinator(hass, {sample_virtual_key.lockMac: conn})
    coordinator.async_apply_advertisement(
        sample_virtual_key.lockMac,
        _advertisement(unlocked=True, battery=66),
    )
    state = coordinator.data[sample_virtual_key.lockMac]
    assert state["locked"] is False
    assert state["battery_level"] == 66
    conn.async_query_state.assert_not_awaited()


async def test_apply_advertisement_keeps_the_other_locks(hass) -> None:
    coordinator = _coordinator(hass, {})
    coordinator.async_set_updated_data({"OTHER": {"locked": None}})
    coordinator.async_apply_advertisement(
        "AA:BB:CC:DD:EE:FF", _advertisement(unlocked=False)
    )
    assert coordinator.data["OTHER"] == {"locked": None}
    assert coordinator.data["AA:BB:CC:DD:EE:FF"]["locked"] is True


async def test_dormant_advertisement_keeps_the_last_known_state(hass) -> None:
    """The dormancy bit clears the bolt bit with the radio, not with the bolt."""
    coordinator = _coordinator(hass, {})
    coordinator.async_apply_advertisement(
        "AA:BB:CC:DD:EE:FF",
        _advertisement(unlocked=True, battery=66),
    )
    coordinator.async_apply_advertisement(
        "AA:BB:CC:DD:EE:FF",
        _advertisement(unlocked=False, battery=64, dormant=True),
    )
    state = coordinator.data["AA:BB:CC:DD:EE:FF"]
    assert state["locked"] is False
    assert state["battery_level"] == 64


async def test_dormant_advertisement_reports_no_state_when_none_is_known(hass) -> None:
    coordinator = _coordinator(hass, {})
    coordinator.async_apply_advertisement(
        "AA:BB:CC:DD:EE:FF",
        _advertisement(unlocked=False, dormant=True),
    )
    state = coordinator.data["AA:BB:CC:DD:EE:FF"]
    assert state["locked"] is None
    assert state["battery_level"] == 66
    assert coordinator.async_has_state("AA:BB:CC:DD:EE:FF") is False


async def test_has_state_is_false_until_a_lock_state_is_known(hass) -> None:
    coordinator = _coordinator(hass, {})
    assert coordinator.async_has_state("AA:BB:CC:DD:EE:FF") is False
    coordinator.async_set_updated_data(
        {"AA:BB:CC:DD:EE:FF": {"locked": None}},
    )
    assert coordinator.async_has_state("AA:BB:CC:DD:EE:FF") is False
    coordinator.async_apply_advertisement(
        "AA:BB:CC:DD:EE:FF", _advertisement(unlocked=False)
    )
    assert coordinator.async_has_state("AA:BB:CC:DD:EE:FF") is True


async def test_poll_that_raises_blanks_only_that_lock(hass, sample_virtual_key) -> None:
    """One lock throwing must not take the others' readings down with it."""
    other = "11:BB:CC:DD:EE:FF"
    failing = _mock_connection()
    failing.async_query_state = AsyncMock(side_effect=RuntimeError("adapter gone"))
    coordinator = _coordinator(
        hass,
        {
            sample_virtual_key.lockMac: failing,
            other: _mock_connection(query_return=(1, 50)),
        },
    )
    data = await coordinator._async_update_data()
    assert data[sample_virtual_key.lockMac] == {"locked": None, "battery_level": None}
    assert data[other]["locked"] is False


MAC = "AA:BB:CC:DD:EE:FF"


def _log_coordinator(hass, conn):
    coordinator = _coordinator(hass, {MAC: conn})
    coordinator.config_entry = _task_entry(hass)
    return coordinator


async def test_advertised_records_trigger_a_log_read(hass) -> None:
    """A keypad unlock reaches the event entity without waiting for the poll."""
    conn = _mock_connection()
    coordinator = _log_coordinator(hass, conn)
    coordinator.async_apply_advertisement(
        MAC, _advertisement(unlocked=False, records=True)
    )
    await hass.async_block_till_done()
    conn.async_get_operation_log.assert_awaited_once()


async def test_advertised_records_read_once_per_cooldown(hass) -> None:
    """The flag stays up until the cursor syncs; reads must be spaced, not repeated."""
    conn = _mock_connection()
    coordinator = _log_coordinator(hass, conn)
    for _ in range(3):
        coordinator.async_apply_advertisement(
            MAC, _advertisement(unlocked=False, records=True)
        )
        await hass.async_block_till_done()
    conn.async_get_operation_log.assert_awaited_once()


async def test_unreachable_lock_is_retried_after_the_cooldown(hass) -> None:
    """An unreachable lock reports nothing rather than raising, keeping the flag up."""

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    from custom_components.ttlock_ble.coordinator import LOG_RETRY_COOLDOWN_SECONDS

    conn = _mock_connection()
    conn.async_get_operation_log = AsyncMock(return_value=[])
    coordinator = _log_coordinator(hass, conn)
    coordinator.async_apply_advertisement(
        MAC, _advertisement(unlocked=False, records=True)
    )
    await hass.async_block_till_done()
    async_fire_time_changed(
        hass,
        dt_util.utcnow() + timedelta(seconds=LOG_RETRY_COOLDOWN_SECONDS + 1),
    )
    await hass.async_block_till_done()
    assert conn.async_get_operation_log.await_count == 2


async def test_flag_going_down_releases_the_lock_for_the_next_record(hass) -> None:
    """A record written right after a successful read must not wait a cooldown out."""
    conn = _mock_connection()
    coordinator = _log_coordinator(hass, conn)
    for records in (True, False, True):
        coordinator.async_apply_advertisement(
            MAC, _advertisement(unlocked=False, records=records)
        )
        await hass.async_block_till_done()
    assert conn.async_get_operation_log.await_count == 2


async def test_advertisement_without_records_reads_nothing(hass) -> None:
    conn = _mock_connection()
    coordinator = _log_coordinator(hass, conn)
    coordinator.async_apply_advertisement(MAC, _advertisement(unlocked=True))
    await hass.async_block_till_done()
    conn.async_get_operation_log.assert_not_awaited()


async def test_dormant_advertisement_still_reads_the_log(hass) -> None:
    """Anything done at the door is recorded, then the lock goes back to sleep."""
    conn = _mock_connection()
    coordinator = _log_coordinator(hass, conn)
    with patch.object(coordinator, "async_request_refresh"):
        coordinator.async_apply_advertisement(
            MAC, _advertisement(unlocked=False, dormant=True, records=True)
        )
        await hass.async_block_till_done()
    conn.async_get_operation_log.assert_awaited_once()


async def test_advertised_log_read_failure_is_contained(hass) -> None:
    conn = _mock_connection()
    conn.async_get_operation_log = AsyncMock(side_effect=RuntimeError("link dropped"))
    coordinator = _log_coordinator(hass, conn)
    coordinator.async_apply_advertisement(
        MAC, _advertisement(unlocked=False, records=True)
    )
    await hass.async_block_till_done()
    conn.async_get_operation_log.assert_awaited_once()


async def test_advertised_records_for_an_unknown_lock_are_ignored(hass) -> None:
    coordinator = _coordinator(hass, {})
    coordinator.config_entry = _task_entry(hass)
    coordinator.async_apply_advertisement(
        "11:22:33:44:55:66", _advertisement(unlocked=False, records=True)
    )
    await hass.async_block_till_done()


async def test_a_pending_read_is_retried_on_a_timer(hass) -> None:
    """The lock repeats the same bytes, and HA does not forward those twice.

    So a read that failed can never be retried by the next advertisement —
    only a timer gets us back to it.
    """

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    from custom_components.ttlock_ble.coordinator import LOG_RETRY_COOLDOWN_SECONDS

    conn = _mock_connection()
    coordinator = _log_coordinator(hass, conn)
    coordinator.async_apply_advertisement(
        MAC, _advertisement(unlocked=False, records=True)
    )
    await hass.async_block_till_done()
    assert conn.async_get_operation_log.await_count == 1

    async_fire_time_changed(
        hass,
        dt_util.utcnow() + timedelta(seconds=LOG_RETRY_COOLDOWN_SECONDS + 1),
    )
    await hass.async_block_till_done()
    assert conn.async_get_operation_log.await_count == 2


async def test_the_retry_stops_once_the_flag_clears(hass) -> None:
    conn = _mock_connection()
    coordinator = _log_coordinator(hass, conn)
    coordinator.async_apply_advertisement(
        MAC, _advertisement(unlocked=False, records=True)
    )
    await hass.async_block_till_done()
    coordinator.async_apply_advertisement(MAC, _advertisement(unlocked=False))
    await hass.async_block_till_done()

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    from custom_components.ttlock_ble.coordinator import LOG_RETRY_COOLDOWN_SECONDS

    async_fire_time_changed(
        hass,
        dt_util.utcnow() + timedelta(seconds=LOG_RETRY_COOLDOWN_SECONDS + 1),
    )
    await hass.async_block_till_done()
    assert conn.async_get_operation_log.await_count == 1


async def test_a_dormant_sighting_reads_the_bolt_position_when_unknown(hass) -> None:
    """A dormant frame has no position, but proves the lock is in range."""
    conn = _mock_connection()
    coordinator = _log_coordinator(hass, conn)
    with patch.object(coordinator, "async_request_refresh") as refresh:
        coordinator.async_apply_advertisement(
            MAC, _advertisement(unlocked=False, dormant=True)
        )
        await hass.async_block_till_done()
    refresh.assert_called_once()


async def test_an_awake_sighting_reads_nothing(hass) -> None:
    """The advertisement already carried the position; there is nothing to ask."""
    conn = _mock_connection()
    coordinator = _log_coordinator(hass, conn)
    with patch.object(coordinator, "async_request_refresh") as refresh:
        coordinator.async_apply_advertisement(MAC, _advertisement(unlocked=False))
        await hass.async_block_till_done()
    refresh.assert_not_called()


async def test_the_read_is_not_repeated_on_every_advertisement(hass) -> None:
    conn = _mock_connection()
    coordinator = _log_coordinator(hass, conn)
    with patch.object(coordinator, "async_request_refresh") as refresh:
        for _ in range(3):
            coordinator.async_apply_advertisement(
                MAC, _advertisement(unlocked=False, dormant=True)
            )
            await hass.async_block_till_done()
    refresh.assert_called_once()


async def test_the_read_is_tried_again_after_the_cooldown(hass) -> None:
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    from custom_components.ttlock_ble.coordinator import STATE_PROBE_COOLDOWN_SECONDS

    conn = _mock_connection()
    coordinator = _log_coordinator(hass, conn)
    with patch.object(coordinator, "async_request_refresh") as refresh:
        coordinator.async_apply_advertisement(
            MAC, _advertisement(unlocked=False, dormant=True)
        )
        await hass.async_block_till_done()
        async_fire_time_changed(
            hass,
            dt_util.utcnow() + timedelta(seconds=STATE_PROBE_COOLDOWN_SECONDS + 1),
        )
        await hass.async_block_till_done()
        coordinator.async_apply_advertisement(
            MAC, _advertisement(unlocked=False, dormant=True)
        )
        await hass.async_block_till_done()
    assert refresh.call_count == 2


async def test_a_known_position_stops_the_reads(hass) -> None:
    """Once the lock has been heard awake there is nothing left to ask about."""
    conn = _mock_connection()
    coordinator = _log_coordinator(hass, conn)
    coordinator.async_apply_advertisement(MAC, _advertisement(unlocked=True))
    await hass.async_block_till_done()
    with patch.object(coordinator, "async_request_refresh") as refresh:
        coordinator.async_apply_advertisement(
            MAC, _advertisement(unlocked=False, dormant=True)
        )
        await hass.async_block_till_done()
    refresh.assert_not_called()


async def test_a_sighting_of_an_unknown_lock_reads_nothing(hass) -> None:
    coordinator = _coordinator(hass, {})
    coordinator.config_entry = _task_entry(hass)
    with patch.object(coordinator, "async_request_refresh") as refresh:
        coordinator.async_note_lock_seen("11:22:33:44:55:66")
        await hass.async_block_till_done()
    refresh.assert_not_called()


async def test_learning_the_position_disarms_the_pending_read(hass) -> None:
    """The rate limit exists to space retries, not to outlive their reason."""
    conn = _mock_connection()
    coordinator = _log_coordinator(hass, conn)
    with patch.object(coordinator, "async_request_refresh"):
        coordinator.async_apply_advertisement(
            MAC, _advertisement(unlocked=False, dormant=True)
        )
        await hass.async_block_till_done()
    assert MAC in coordinator._state_probes

    coordinator.async_apply_advertisement(MAC, _advertisement(unlocked=True))
    await hass.async_block_till_done()
    assert MAC not in coordinator._state_probes


def _device_info(**overrides) -> DeviceInfo:
    """Build the SDK's device info with the fields a lock actually answers."""
    fields = {
        "model": "SN534-4P-T78-BELL",
        "hardware_revision": "1.7",
        "firmware_revision": "6.5.20.24121101",
    }
    return DeviceInfo(**{**fields, **overrides})


DESCRIPTION = {
    "model": "SN534-4P-T78-BELL",
    "hardware_version": "1.7",
    "firmware_version": "6.5.20.24121101",
}


async def test_a_poll_learns_what_the_lock_reports_about_itself(hass) -> None:
    conn = _mock_connection()
    conn.async_get_device_info = AsyncMock(return_value=_device_info())
    coordinator = _coordinator(hass, {MAC: conn})

    await coordinator._async_update_data()

    assert coordinator.async_device_description(MAC) == DESCRIPTION


async def test_the_hardware_strings_are_read_once_per_run(hass) -> None:
    """They are static, and each field costs its own BLE round trip."""
    conn = _mock_connection()
    conn.async_get_device_info = AsyncMock(return_value=_device_info())
    coordinator = _coordinator(hass, {MAC: conn})

    await coordinator._async_update_data()
    await coordinator._async_update_data()

    assert conn.async_get_device_info.await_count == 1


async def test_a_read_that_did_not_reach_the_lock_is_tried_again(hass) -> None:
    conn = _mock_connection()
    conn.async_get_device_info = AsyncMock(side_effect=[None, _device_info()])
    coordinator = _coordinator(hass, {MAC: conn})

    await coordinator._async_update_data()
    assert coordinator.async_device_description(MAC) is None

    await coordinator._async_update_data()
    assert coordinator.async_device_description(MAC) == DESCRIPTION


async def test_an_unchanged_description_is_not_written_again(hass) -> None:
    """A restart re-reads the lock; nothing about the device has to move."""
    descriptions = TtlockBleDeviceDescriptionStore(hass)
    descriptions.async_remember(MAC, DESCRIPTION)
    conn = _mock_connection()
    conn.async_get_device_info = AsyncMock(return_value=_device_info())
    coordinator = _coordinator(hass, {MAC: conn}, descriptions=descriptions)

    with patch.object(descriptions, "async_remember") as remember:
        await coordinator._async_update_data()

    remember.assert_not_called()


async def test_the_hardware_strings_reach_the_registry_device(
    hass,
    enable_custom_integrations,
) -> None:
    """`device_info` is only read at registration, so the device is updated in place."""
    from homeassistant.helpers import device_registry
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id="u")
    entry.add_to_hass(hass)
    registry = device_registry.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, MAC.lower())},
        model="Protocol 5.3",
    )
    conn = _mock_connection()
    conn.async_get_device_info = AsyncMock(return_value=_device_info())
    coordinator = _coordinator(hass, {MAC: conn})

    await coordinator._async_update_data()

    device = registry.async_get_device(identifiers={(DOMAIN, MAC.lower())})
    assert device is not None
    assert device.model == "SN534-4P-T78-BELL"
    assert device.hw_version == "1.7"
    assert device.sw_version == "6.5.20.24121101"


async def test_a_field_the_lock_leaves_out_keeps_what_the_device_had(
    hass,
    enable_custom_integrations,
) -> None:
    """The protocol version is worth more on the device than an empty model."""
    from homeassistant.helpers import device_registry
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id="u")
    entry.add_to_hass(hass)
    registry = device_registry.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, MAC.lower())},
        model="Protocol 5.3",
    )
    conn = _mock_connection()
    conn.async_get_device_info = AsyncMock(return_value=_device_info(model=None))
    coordinator = _coordinator(hass, {MAC: conn})

    await coordinator._async_update_data()

    device = registry.async_get_device(identifiers={(DOMAIN, MAC.lower())})
    assert device is not None
    assert device.model == "Protocol 5.3"
    assert device.sw_version == "6.5.20.24121101"


async def test_a_lock_with_no_registry_device_is_still_remembered(hass) -> None:
    """Nothing to stamp yet — the description still has to survive to setup."""
    conn = _mock_connection()
    conn.async_get_device_info = AsyncMock(return_value=_device_info())
    coordinator = _coordinator(hass, {MAC: conn})

    await coordinator._async_update_data()

    assert coordinator.async_device_description(MAC) == DESCRIPTION


async def test_shutdown_cancels_the_pending_log_retry(hass) -> None:
    """Left armed, the retry re-arms itself for the rest of the HA run."""
    conn = _mock_connection()
    coordinator = _log_coordinator(hass, conn)
    with patch.object(coordinator, "async_request_refresh"):
        coordinator.async_apply_advertisement(
            MAC, _advertisement(unlocked=False, records=True)
        )
        await hass.async_block_till_done()
    assert MAC in coordinator._log_retries

    await coordinator.async_shutdown()

    assert coordinator._log_retries == {}


async def test_shutdown_cancels_the_pending_state_probe(hass) -> None:
    conn = _mock_connection()
    coordinator = _log_coordinator(hass, conn)
    with patch.object(coordinator, "async_request_refresh"):
        coordinator.async_apply_advertisement(
            MAC, _advertisement(unlocked=False, dormant=True)
        )
        await hass.async_block_till_done()
    assert MAC in coordinator._state_probes

    await coordinator.async_shutdown()

    assert coordinator._state_probes == {}


async def test_a_cancelled_retry_never_fires_again(hass) -> None:
    """The unloaded entry must not keep reading a lock it no longer owns."""

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    from custom_components.ttlock_ble.coordinator import LOG_RETRY_COOLDOWN_SECONDS

    conn = _mock_connection()
    coordinator = _log_coordinator(hass, conn)
    with patch.object(coordinator, "async_request_refresh"):
        coordinator.async_apply_advertisement(
            MAC, _advertisement(unlocked=False, records=True)
        )
        await hass.async_block_till_done()
    await coordinator.async_shutdown()
    conn.async_get_operation_log.reset_mock()

    async_fire_time_changed(
        hass,
        dt_util.utcnow() + timedelta(seconds=LOG_RETRY_COOLDOWN_SECONDS + 1),
    )
    await hass.async_block_till_done()

    conn.async_get_operation_log.assert_not_awaited()


MAC = "AA:BB:CC:DD:EE:FF"


def _clock_connection(*, lock_offset_seconds: float, admin_ps: str = "135792468"):
    """A connection whose lock answers a clock `lock_offset_seconds` off local time."""
    conn = _mock_connection()
    conn.key = MagicMock(lockMac=MAC, adminPs=admin_ps)
    naive_now = dt_util.now().replace(tzinfo=None)
    conn.async_get_lock_time = AsyncMock(
        return_value=naive_now + dt.timedelta(seconds=lock_offset_seconds)
    )
    conn.async_calibrate_time = AsyncMock(return_value=True)
    return conn


async def test_a_healthy_clock_is_measured_and_left_alone(hass) -> None:
    """Within the threshold there is nothing to write, and writing costs battery."""
    conn = _clock_connection(lock_offset_seconds=1.0)
    coordinator = _coordinator(hass, {MAC: conn})

    await coordinator._async_update_data()

    conn.async_get_lock_time.assert_awaited_once()
    conn.async_calibrate_time.assert_not_awaited()
    sync = coordinator.async_clock_sync(MAC)
    assert sync is not None
    assert abs(sync["drift_seconds"]) < CLOCK_DRIFT_THRESHOLD_SECONDS


async def test_a_drifted_clock_is_corrected(hass) -> None:
    conn = _clock_connection(lock_offset_seconds=-600.0)
    coordinator = _coordinator(hass, {MAC: conn})

    await coordinator._async_update_data()

    conn.async_calibrate_time.assert_awaited_once()
    written = conn.async_calibrate_time.await_args.args[0]
    assert written.tzinfo is None
    # Written from a reference taken at the write, not the stale one the
    # comparison used - reusing that would put the lock a round trip behind.
    assert abs((written - dt_util.now().replace(tzinfo=None)).total_seconds()) < 5
    assert (
        coordinator.async_clock_sync(MAC)["drift_seconds"]
        < -CLOCK_DRIFT_THRESHOLD_SECONDS
    )


async def test_a_key_with_no_admin_password_still_reports_its_drift(hass) -> None:
    """The read is unauthenticated; only the correction needs an admin password."""
    conn = _clock_connection(lock_offset_seconds=-600.0, admin_ps="")
    coordinator = _coordinator(hass, {MAC: conn})

    await coordinator._async_update_data()

    conn.async_calibrate_time.assert_not_awaited()
    assert coordinator.async_clock_sync(MAC) is not None


async def test_an_unreachable_clock_records_nothing(hass) -> None:
    """A failed read must not stamp a check that never happened."""
    conn = _clock_connection(lock_offset_seconds=0.0)
    conn.async_get_lock_time = AsyncMock(return_value=None)
    coordinator = _coordinator(hass, {MAC: conn})

    await coordinator._async_update_data()

    assert coordinator.async_clock_sync(MAC) is None
    conn.async_calibrate_time.assert_not_awaited()


async def test_the_clock_is_checked_at_most_once_a_day(hass) -> None:
    conn = _clock_connection(lock_offset_seconds=1.0)
    coordinator = _coordinator(hass, {MAC: conn})

    await coordinator._async_update_data()
    await coordinator._async_update_data()

    conn.async_get_lock_time.assert_awaited_once()


async def test_the_clock_is_checked_again_once_the_interval_has_passed(hass) -> None:
    conn = _clock_connection(lock_offset_seconds=1.0)
    clock_syncs = TtlockBleClockSyncStore(hass)
    stale = dt_util.utcnow() - dt.timedelta(seconds=CLOCK_CHECK_INTERVAL_SECONDS + 60)
    clock_syncs.async_remember(
        MAC,
        {"checked_at": stale.isoformat(), "drift_seconds": 0.0},
    )
    coordinator = _coordinator(hass, {MAC: conn}, clock_syncs=clock_syncs)

    await coordinator._async_update_data()

    conn.async_get_lock_time.assert_awaited_once()


async def test_an_unreadable_stored_timestamp_is_treated_as_never_checked(hass) -> None:
    """A record that cannot be parsed must not wedge the check off forever."""
    conn = _clock_connection(lock_offset_seconds=1.0)
    clock_syncs = TtlockBleClockSyncStore(hass)
    clock_syncs.async_remember(MAC, {"checked_at": "not a date", "drift_seconds": 0.0})
    coordinator = _coordinator(hass, {MAC: conn}, clock_syncs=clock_syncs)

    await coordinator._async_update_data()

    conn.async_get_lock_time.assert_awaited_once()


async def test_a_correction_that_never_reaches_the_lock_is_survivable(hass) -> None:
    conn = _clock_connection(lock_offset_seconds=-600.0)
    conn.async_calibrate_time = AsyncMock(return_value=False)
    coordinator = _coordinator(hass, {MAC: conn})

    await coordinator._async_update_data()

    conn.async_calibrate_time.assert_awaited_once()


async def test_the_log_read_carries_the_clock_check(hass) -> None:
    """An advertised log read is the session a mostly idle lock actually grants."""
    conn = _clock_connection(lock_offset_seconds=1.0)
    coordinator = _coordinator(hass, {MAC: conn})

    await coordinator._async_fetch_operation_log(MAC, conn)

    conn.async_get_lock_time.assert_awaited_once()


async def test_a_failed_log_read_carries_no_clock_check(hass) -> None:
    """A read that never landed is no proof of a session to ride on."""
    conn = _clock_connection(lock_offset_seconds=1.0)
    conn.async_get_operation_log = AsyncMock(side_effect=ValueError("garbled frame"))
    coordinator = _coordinator(hass, {MAC: conn})

    await coordinator._async_fetch_operation_log(MAC, conn)

    conn.async_get_lock_time.assert_not_awaited()
