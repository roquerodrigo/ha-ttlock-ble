from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bleak import BleakError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from ttlock_ble import DeviceInfo, LockEvent, TTLockError

from custom_components.ttlock_ble.connection import (
    TtlockBleConnection,
    connection_signal,
    event_signal,
    log_signal,
)
from custom_components.ttlock_ble.data import TtlockBleLogCursor


def _log_entry(record_number: int) -> SimpleNamespace:
    """Build a minimal LogEntry stand-in keyed by `record_number`."""
    return SimpleNamespace(record_number=record_number)


def test_event_signal_lowercases_mac() -> None:
    assert event_signal("AA:BB:CC:DD:EE:FF") == "ttlock_ble_event_aa:bb:cc:dd:ee:ff"


def test_connection_signal_lowercases_mac() -> None:
    assert (
        connection_signal("AA:BB:CC:DD:EE:FF")
        == "ttlock_ble_connection_aa:bb:cc:dd:ee:ff"
    )


async def test_is_connected_false_before_start(hass, sample_virtual_key) -> None:
    conn = TtlockBleConnection(hass, sample_virtual_key)
    assert conn.is_connected is False


async def test_key_exposed(hass, sample_virtual_key) -> None:
    conn = TtlockBleConnection(hass, sample_virtual_key)
    assert conn.key is sample_virtual_key


async def test_query_state_returns_none_when_device_missing(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    mock_ble_resolver.return_value = None
    conn = TtlockBleConnection(hass, sample_virtual_key)
    assert await conn.async_query_state() is None
    mock_ttlock_client.connect.assert_not_awaited()


async def test_query_state_returns_none_when_connect_fails(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    mock_ttlock_client.connect = AsyncMock(side_effect=TTLockError("ble fail"))
    conn = TtlockBleConnection(hass, sample_virtual_key)
    assert await conn.async_query_state() is None


async def test_query_state_happy_path(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    mock_ttlock_client.query_state = AsyncMock(return_value=(0, 88))
    conn = TtlockBleConnection(hass, sample_virtual_key)
    assert await conn.async_query_state() == (0, 88)
    mock_ttlock_client.add_event_listener.assert_called_once()


async def test_query_state_disconnects_on_ttlock_error(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    mock_ttlock_client.query_state = AsyncMock(side_effect=TTLockError("read fail"))
    conn = TtlockBleConnection(hass, sample_virtual_key)
    result = await conn.async_query_state()
    assert result is None
    mock_ttlock_client.disconnect.assert_awaited()


async def test_query_state_reuses_open_connection(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    conn = TtlockBleConnection(hass, sample_virtual_key)
    await conn.async_query_state()
    await conn.async_query_state()
    # Only one BLE connect because the client stays connected.
    assert mock_ttlock_client.connect.await_count == 1


async def test_lock_happy(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    conn = TtlockBleConnection(hass, sample_virtual_key)
    await conn.async_lock()
    mock_ttlock_client.lock.assert_awaited_once()


async def test_unlock_happy(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    conn = TtlockBleConnection(hass, sample_virtual_key)
    await conn.async_unlock()
    mock_ttlock_client.unlock.assert_awaited_once()


async def test_lock_raises_when_device_missing(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
) -> None:
    mock_ble_resolver.return_value = None
    conn = TtlockBleConnection(hass, sample_virtual_key)
    with pytest.raises(TTLockError, match="not reachable"):
        await conn.async_lock()


async def test_lock_propagates_and_disconnects_on_command_error(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    mock_ttlock_client.lock = AsyncMock(side_effect=TTLockError("bad psFromLock"))
    conn = TtlockBleConnection(hass, sample_virtual_key)
    with pytest.raises(TTLockError, match="bad psFromLock"):
        await conn.async_lock()
    mock_ttlock_client.disconnect.assert_awaited()


async def test_event_listener_dispatches_to_signal(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    received: list[LockEvent] = []
    async_dispatcher_connect(
        hass,
        event_signal(sample_virtual_key.lockMac),
        received.append,
    )
    conn = TtlockBleConnection(hass, sample_virtual_key)
    await conn.async_query_state()
    listener = mock_ttlock_client.add_event_listener.call_args[0][0]
    pushed = LockEvent(cmd_echo=0x47, status=1, data=b"\x01")
    listener(pushed)
    await hass.async_block_till_done()
    assert received == [pushed]


async def test_disconnect_swallows_exceptions(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    mock_ttlock_client.disconnect = AsyncMock(side_effect=RuntimeError("boom"))
    conn = TtlockBleConnection(hass, sample_virtual_key)
    await conn.async_query_state()
    await conn.async_stop()
    assert conn.is_connected is False


async def test_async_start_creates_task(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    conn = TtlockBleConnection(hass, sample_virtual_key)
    with patch.multiple(
        "custom_components.ttlock_ble.connection",
        RECONNECT_INITIAL_BACKOFF=0.01,
        RECONNECT_MAX_BACKOFF=0.05,
    ):
        await conn.async_start()
        await asyncio.sleep(0.05)
        await conn.async_stop()
    assert conn.is_connected is False


async def test_async_start_idempotent(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    conn = TtlockBleConnection(hass, sample_virtual_key)
    with patch.multiple(
        "custom_components.ttlock_ble.connection",
        RECONNECT_INITIAL_BACKOFF=0.01,
        RECONNECT_MAX_BACKOFF=0.05,
    ):
        await conn.async_start()
        first_task = conn._task
        await conn.async_start()
        assert conn._task is first_task
        await conn.async_stop()


async def test_async_stop_without_start_is_safe(hass, sample_virtual_key) -> None:
    conn = TtlockBleConnection(hass, sample_virtual_key)
    await conn.async_stop()


async def test_maintain_loop_keeps_trying_when_device_missing(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    mock_ble_resolver.return_value = None
    conn = TtlockBleConnection(hass, sample_virtual_key)
    with patch.multiple(
        "custom_components.ttlock_ble.connection",
        RECONNECT_INITIAL_BACKOFF=0.005,
        RECONNECT_MAX_BACKOFF=0.01,
    ):
        await conn.async_start()
        await asyncio.sleep(0.05)
        await conn.async_stop()
    # The resolver must have been hit multiple times by the maintain loop.
    assert mock_ble_resolver.call_count >= 2


async def test_maintain_loop_logs_unexpected_error(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    # Make ensure_connected raise a non-CancelledError so the broad except branch runs.
    mock_ble_resolver.side_effect = [RuntimeError("kaboom"), None, None, None]
    conn = TtlockBleConnection(hass, sample_virtual_key)
    with patch.multiple(
        "custom_components.ttlock_ble.connection",
        RECONNECT_INITIAL_BACKOFF=0.005,
        RECONNECT_MAX_BACKOFF=0.01,
    ):
        await conn.async_start()
        await asyncio.sleep(0.05)
        await conn.async_stop()
    assert mock_ble_resolver.call_count >= 1


async def test_query_state_reads_without_a_maintain_loop(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """Without the permanent connection nothing is running; a read still connects."""
    mock_ttlock_client.query_state = AsyncMock(return_value=(0, 90))
    conn = TtlockBleConnection(hass, sample_virtual_key)
    assert await conn.async_query_state() == (0, 90)


async def test_the_maintain_loop_reconnects_straight_after_a_drop(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """That storm is the permanent connection: the lock drops idle sessions fast."""
    conn = TtlockBleConnection(hass, sample_virtual_key)
    with patch.multiple(
        "custom_components.ttlock_ble.connection",
        RECONNECT_INITIAL_BACKOFF=0.005,
        RECONNECT_MAX_BACKOFF=0.01,
    ):
        await conn.async_start()
        for _ in range(20):
            await asyncio.sleep(0.005)
            if mock_ttlock_client.connect.await_count >= 1:
                break
        connects_before_drop = mock_ttlock_client.connect.await_count
        mock_ttlock_client.is_connected = False
        conn._on_disconnected(mock_ttlock_client)
        for _ in range(20):
            await asyncio.sleep(0.005)
            if mock_ttlock_client.connect.await_count > connects_before_drop:
                break
        assert mock_ttlock_client.connect.await_count > connects_before_drop
        await conn.async_stop()


async def test_connection_signal_fires_on_connect_and_disconnect(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """Successful connect emits True; tearing the session down emits False."""
    received: list[bool] = []
    async_dispatcher_connect(
        hass,
        connection_signal(sample_virtual_key.lockMac),
        received.append,
    )
    conn = TtlockBleConnection(hass, sample_virtual_key)
    await conn.async_query_state()
    await hass.async_block_till_done()
    assert received == [True]
    await conn.async_stop()
    await hass.async_block_till_done()
    assert received == [True, False]


async def test_connection_signal_not_emitted_when_connect_fails(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """If BLE connect raises, nothing is broadcast — state stayed `down`."""
    received: list[bool] = []
    async_dispatcher_connect(
        hass,
        connection_signal(sample_virtual_key.lockMac),
        received.append,
    )
    mock_ttlock_client.connect = AsyncMock(side_effect=TTLockError("ble fail"))
    conn = TtlockBleConnection(hass, sample_virtual_key)
    await conn.async_query_state()
    await hass.async_block_till_done()
    assert received == []


async def test_get_operation_log_returns_empty_when_device_missing(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """No reachable device means no client, so the log fetch yields nothing."""
    mock_ble_resolver.return_value = None
    conn = TtlockBleConnection(hass, sample_virtual_key)
    assert await conn.async_get_operation_log() == []
    mock_ttlock_client.get_operation_log.assert_not_called()


async def test_get_operation_log_returns_empty_on_ttlock_error(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """A TTLockError during the fetch is swallowed and returns an empty list."""
    mock_ttlock_client.get_operation_log = AsyncMock(
        side_effect=TTLockError("read log fail"),
    )
    conn = TtlockBleConnection(hass, sample_virtual_key)
    assert await conn.async_get_operation_log() == []


@pytest.mark.parametrize(
    "error",
    [
        ValueError(
            "The length of the provided data is not a multiple of the block length"
        ),
        RuntimeError("lock rejected checkUserTime"),
    ],
)
async def test_get_operation_log_returns_empty_on_unwrapped_error(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
    error: Exception,
) -> None:
    """The SDK's log path raises outside TTLockError; the fetch still returns []."""
    mock_ttlock_client.get_operation_log = AsyncMock(side_effect=error)
    conn = TtlockBleConnection(hass, sample_virtual_key)
    assert await conn.async_get_operation_log() == []


async def test_get_operation_log_dispatches_only_new_records(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """Each record is dispatched once; subsequent fetches skip seen records."""
    received: list[object] = []
    async_dispatcher_connect(
        hass,
        log_signal(sample_virtual_key.lockMac),
        received.append,
    )
    first = [_log_entry(1), _log_entry(2)]
    mock_ttlock_client.get_operation_log = AsyncMock(return_value=first)
    conn = TtlockBleConnection(hass, sample_virtual_key)

    # The first successful fetch is the seeding pass: the backlog is history.
    new_entries = await conn.async_get_operation_log()
    await hass.async_block_till_done()
    assert new_entries == []
    assert received == []

    # A later fetch returning the same records plus a new one only emits the new.
    second = [_log_entry(1), _log_entry(2), _log_entry(3)]
    mock_ttlock_client.get_operation_log = AsyncMock(return_value=second)
    new_entries = await conn.async_get_operation_log()
    await hass.async_block_till_done()
    assert [e.record_number for e in new_entries] == [3]
    assert [e.record_number for e in received] == [3]


async def test_seeding_waits_for_a_fetch_that_reached_the_lock(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """A lock out of range at startup must not spend its seeding pass."""
    received: list[object] = []
    async_dispatcher_connect(
        hass,
        log_signal(sample_virtual_key.lockMac),
        received.append,
    )
    conn = TtlockBleConnection(hass, sample_virtual_key)

    # Out of range: no client, so nothing was seen and nothing was seeded.
    with patch(
        "custom_components.ttlock_ble.connection.async_ble_device_from_address",
        return_value=None,
    ):
        assert await conn.async_get_operation_log() == []

    # And the fetch that does reach the lock is still the seeding pass.
    backlog = [_log_entry(1), _log_entry(2), _log_entry(3)]
    mock_ttlock_client.get_operation_log = AsyncMock(return_value=backlog)
    assert await conn.async_get_operation_log() == []
    await hass.async_block_till_done()
    assert received == []


async def test_seeding_is_not_spent_by_a_failed_fetch(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """A fetch that raised did not observe the backlog, so it cannot seed."""
    received: list[object] = []
    async_dispatcher_connect(
        hass,
        log_signal(sample_virtual_key.lockMac),
        received.append,
    )
    conn = TtlockBleConnection(hass, sample_virtual_key)
    mock_ttlock_client.get_operation_log = AsyncMock(
        side_effect=TTLockError("read log fail"),
    )
    assert await conn.async_get_operation_log() == []

    mock_ttlock_client.get_operation_log = AsyncMock(return_value=[_log_entry(9)])
    assert await conn.async_get_operation_log() == []
    await hass.async_block_till_done()
    assert received == []


async def test_run_command_wraps_timeout_error(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """A bare `TimeoutError` from the SDK is converted to a `TTLockError`."""
    mock_ttlock_client.lock = AsyncMock(side_effect=TimeoutError)
    conn = TtlockBleConnection(hass, sample_virtual_key)
    with pytest.raises(TTLockError, match="timed out responding to lock"):
        await conn.async_lock()
    mock_ttlock_client.disconnect.assert_awaited()


@pytest.mark.parametrize(
    "escape",
    [
        RuntimeError("checkUserTime FAILED: status=0x0 err=03"),
        ValueError("invalid padding"),
        OSError("le-connection-abort-by-local"),
    ],
)
async def test_run_command_wraps_non_ttlock_escapes(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
    escape,
) -> None:
    """Exceptions the SDK does not wrap still reach callers as `TTLockError`."""
    mock_ttlock_client.unlock = AsyncMock(side_effect=escape)
    conn = TtlockBleConnection(hass, sample_virtual_key)
    with pytest.raises(TTLockError, match="failed to unlock"):
        await conn.async_unlock()
    mock_ttlock_client.disconnect.assert_awaited()


async def test_drop_is_broadcast_immediately_and_only_once(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """The down edge must not wait for the reconnect cooldown to elapse."""
    from custom_components.ttlock_ble.connection import connection_signal

    received: list[bool] = []
    async_dispatcher_connect(
        hass,
        connection_signal(sample_virtual_key.lockMac),
        received.append,
    )
    conn = TtlockBleConnection(hass, sample_virtual_key)
    await conn.async_query_state()
    await hass.async_block_till_done()
    assert received == [True]

    # bleak reports the drop; the teardown that follows must not repeat it.
    mock_ttlock_client.is_connected = False
    conn._on_disconnected(mock_ttlock_client)
    await hass.async_block_till_done()
    assert received == [True, False]

    await conn.async_stop()
    await hass.async_block_till_done()
    assert received == [True, False]


async def test_get_operation_log_is_bounded(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """The fetch holds the same lock commands need, so it has to be bounded."""
    from custom_components.ttlock_ble.connection import MAX_LOG_ENTRIES_PER_FETCH

    conn = TtlockBleConnection(hass, sample_virtual_key)
    await conn.async_get_operation_log()
    assert (
        mock_ttlock_client.get_operation_log.await_args.kwargs["max_entries"]
        == MAX_LOG_ENTRIES_PER_FETCH
    )


async def test_stopped_connection_refuses_to_reconnect(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """A late caller must not reopen the lock's single slot after unload."""
    conn = TtlockBleConnection(hass, sample_virtual_key)
    await conn.async_query_state()
    mock_ttlock_client.connect.reset_mock()
    await conn.async_stop()

    assert await conn.async_query_state() is None
    assert await conn.async_get_operation_log() == []
    with pytest.raises(TTLockError, match="not reachable"):
        await conn.async_lock()
    mock_ttlock_client.connect.assert_not_awaited()


async def test_run_command_lets_cancellation_through(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """Cancellation is not swallowed by the catch-all — callers must see it."""
    import asyncio

    mock_ttlock_client.lock = AsyncMock(side_effect=asyncio.CancelledError)
    conn = TtlockBleConnection(hass, sample_virtual_key)
    with pytest.raises(asyncio.CancelledError):
        await conn.async_lock()


async def test_restored_cursor_dispatches_without_a_seeding_pass(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """A restart resumes where the previous run stopped, so nothing is swallowed."""
    received: list[object] = []
    async_dispatcher_connect(
        hass,
        log_signal(sample_virtual_key.lockMac),
        received.append,
    )
    conn = TtlockBleConnection(
        hass,
        sample_virtual_key,
        log_cursor=TtlockBleLogCursor(records={1, 2}, seeded=True),
    )

    mock_ttlock_client.get_operation_log = AsyncMock(
        return_value=[_log_entry(1), _log_entry(2), _log_entry(3)],
    )
    new_entries = await conn.async_get_operation_log()
    await hass.async_block_till_done()
    assert [e.record_number for e in new_entries] == [3]
    assert [e.record_number for e in received] == [3]


async def test_an_empty_restored_cursor_still_seeds(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """A lock seen for the first time has a backlog that is history, not events."""
    conn = TtlockBleConnection(
        hass, sample_virtual_key, log_cursor=TtlockBleLogCursor()
    )
    mock_ttlock_client.get_operation_log = AsyncMock(
        return_value=[_log_entry(1), _log_entry(2)],
    )
    assert await conn.async_get_operation_log() == []


async def test_the_cursor_is_reported_as_it_moves(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    remembered: list[set[int]] = []
    conn = TtlockBleConnection(
        hass,
        sample_virtual_key,
        log_cursor=TtlockBleLogCursor(
            records={1},
            seeded=True,
            on_move=lambda seen: remembered.append(set(seen)),
        ),
    )
    mock_ttlock_client.get_operation_log = AsyncMock(
        return_value=[_log_entry(1), _log_entry(2)],
    )
    await conn.async_get_operation_log()
    assert remembered == [{1, 2}]


async def test_the_cursor_is_not_reported_when_nothing_is_new(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    remembered: list[set[int]] = []
    conn = TtlockBleConnection(
        hass,
        sample_virtual_key,
        log_cursor=TtlockBleLogCursor(
            records={1, 2},
            seeded=True,
            on_move=lambda seen: remembered.append(set(seen)),
        ),
    )
    mock_ttlock_client.get_operation_log = AsyncMock(
        return_value=[_log_entry(1), _log_entry(2)],
    )
    await conn.async_get_operation_log()
    assert remembered == []


@pytest.mark.parametrize("enabled", [True, False])
async def test_set_lock_sound_reaches_the_lock(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
    enabled,
) -> None:
    conn = TtlockBleConnection(hass, sample_virtual_key)
    await conn.async_set_lock_sound(enabled=enabled)
    mock_ttlock_client.set_lock_sound.assert_awaited_once_with(enabled=enabled)


async def test_set_lock_sound_raises_when_out_of_range(
    hass,
    sample_virtual_key,
    mock_ttlock_client,
) -> None:
    """The caller has to learn the setting did not change."""
    conn = TtlockBleConnection(hass, sample_virtual_key)
    with (
        patch(
            "custom_components.ttlock_ble.connection.async_ble_device_from_address",
            return_value=None,
        ),
        pytest.raises(TTLockError),
    ):
        await conn.async_set_lock_sound(enabled=True)


async def test_device_info_returns_what_the_lock_reports(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    info = DeviceInfo(model="SN534-4P-T78-BELL", firmware_revision="6.5.20.24121101")
    mock_ttlock_client.get_device_info = AsyncMock(return_value=info)
    conn = TtlockBleConnection(hass, sample_virtual_key)
    assert await conn.async_get_device_info() is info


async def test_device_info_returns_none_when_device_missing(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    mock_ble_resolver.return_value = None
    conn = TtlockBleConnection(hass, sample_virtual_key)
    assert await conn.async_get_device_info() is None
    mock_ttlock_client.connect.assert_not_awaited()


async def test_device_info_that_breaks_the_link_costs_nothing_else(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """Hardware strings are not worth failing the poll that carried them."""
    mock_ttlock_client.get_device_info = AsyncMock(side_effect=TTLockError("link down"))
    conn = TtlockBleConnection(hass, sample_virtual_key)
    assert await conn.async_get_device_info() is None


async def test_a_bleak_error_from_connect_is_not_left_raw(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """The SDK leaves `start_notify` unwrapped, so bleak's own error can escape."""
    mock_ttlock_client.connect = AsyncMock(side_effect=BleakError("link dropped"))
    conn = TtlockBleConnection(hass, sample_virtual_key)

    with pytest.raises(TTLockError):
        await conn.async_unlock()
    assert await conn.async_query_state() is None


async def test_a_half_open_session_is_closed_when_connect_fails(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """The lock has one central slot; a session nobody owns has to go back."""
    mock_ttlock_client.connect = AsyncMock(side_effect=BleakError("notify failed"))
    conn = TtlockBleConnection(hass, sample_virtual_key)

    assert await conn.async_query_state() is None

    mock_ttlock_client.disconnect.assert_awaited()
