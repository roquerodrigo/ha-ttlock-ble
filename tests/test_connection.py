from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from ttlock_ble import TTLockError

from custom_components.ttlock_ble.connection import TtlockBleConnection


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
    mock_ttlock_client.disconnect.assert_not_awaited()


async def test_query_state_returns_value_and_disconnects(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    mock_ttlock_client.query_state = AsyncMock(return_value=(0, 88))
    conn = TtlockBleConnection(hass, sample_virtual_key)
    assert await conn.async_query_state() == (0, 88)
    mock_ttlock_client.disconnect.assert_awaited_once()


async def test_query_state_returns_none_on_ttlock_error_and_disconnects(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    mock_ttlock_client.query_state = AsyncMock(side_effect=TTLockError("read fail"))
    conn = TtlockBleConnection(hass, sample_virtual_key)
    assert await conn.async_query_state() is None
    mock_ttlock_client.disconnect.assert_awaited_once()


async def test_each_query_opens_a_fresh_session(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    """On-demand model: every public call connects + disconnects."""
    conn = TtlockBleConnection(hass, sample_virtual_key)
    await conn.async_query_state()
    await conn.async_query_state()
    assert mock_ttlock_client.connect.await_count == 2
    assert mock_ttlock_client.disconnect.await_count == 2


async def test_lock_happy_disconnects_after(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    conn = TtlockBleConnection(hass, sample_virtual_key)
    await conn.async_lock()
    mock_ttlock_client.lock.assert_awaited_once()
    mock_ttlock_client.disconnect.assert_awaited_once()


async def test_unlock_happy_disconnects_after(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    conn = TtlockBleConnection(hass, sample_virtual_key)
    await conn.async_unlock()
    mock_ttlock_client.unlock.assert_awaited_once()
    mock_ttlock_client.disconnect.assert_awaited_once()


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
    mock_ttlock_client.disconnect.assert_awaited_once()


async def test_lock_wraps_timeout_as_ttlock_error(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    mock_ttlock_client.lock = AsyncMock(side_effect=TimeoutError)
    conn = TtlockBleConnection(hass, sample_virtual_key)
    with pytest.raises(TTLockError, match="timed out responding to lock"):
        await conn.async_lock()
    mock_ttlock_client.disconnect.assert_awaited_once()


async def test_disconnect_swallows_exceptions(
    hass,
    sample_virtual_key,
    mock_ble_resolver,
    mock_ttlock_client,
) -> None:
    mock_ttlock_client.disconnect = AsyncMock(side_effect=RuntimeError("boom"))
    conn = TtlockBleConnection(hass, sample_virtual_key)
    # Should still return the state cleanly even though disconnect raised.
    result = await conn.async_query_state()
    assert result == (0, 80)
    mock_ttlock_client.disconnect.assert_awaited_once()
