from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from ttlock_ble import LockEvent, TTLockError

from custom_components.ttlock_ble.connection import (
    TtlockBleConnection,
    connection_signal,
    event_signal,
)


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


async def test_query_state_force_bypass_during_cooldown(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """`force_cooldown_bypass=True` connects even while a cooldown is active."""
    import time

    mock_ttlock_client.query_state = AsyncMock(return_value=(0, 90))
    conn = TtlockBleConnection(hass, sample_virtual_key)
    conn._cooldown_until = time.monotonic() + 60.0
    assert await conn.async_query_state(force_cooldown_bypass=True) == (0, 90)


async def test_query_state_short_circuits_during_cooldown(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """While `_cooldown_until` is in the future, queries return None without BLE I/O."""
    import time

    conn = TtlockBleConnection(hass, sample_virtual_key)
    conn._cooldown_until = time.monotonic() + 60.0
    assert await conn.async_query_state() is None
    mock_ble_resolver.assert_not_called()
    mock_ttlock_client.connect.assert_not_awaited()


async def test_lock_command_bypasses_cooldown(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """User-initiated `async_lock` still tries to connect during cooldown."""
    import time

    conn = TtlockBleConnection(hass, sample_virtual_key)
    conn._cooldown_until = time.monotonic() + 60.0
    await conn.async_lock()
    mock_ttlock_client.lock.assert_awaited_once()


async def test_on_disconnected_wakes_maintain_loop(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    conn = TtlockBleConnection(hass, sample_virtual_key)
    await conn.async_query_state()
    # Simulate bleak's disconnected_callback firing.
    assert not conn._disconnected.is_set()
    conn._on_disconnected(mock_ttlock_client)
    assert conn._disconnected.is_set()


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
