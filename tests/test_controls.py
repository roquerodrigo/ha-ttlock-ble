"""Unit tests for TTLock BLE control entities (auto-lock slider, auto-lock switch, passage mode switch)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.ttlock_ble.number import TtlockBleAutoLockTimeNumber
from custom_components.ttlock_ble.switch import (
    TtlockBleAutoLockSwitch,
    TtlockBlePassageModeSwitch,
)
from ttlock_ble import TTLockError


@pytest.mark.asyncio
async def test_auto_lock_number_entity() -> None:
    """Test auto-lock time number entity."""
    coordinator = MagicMock()
    key = MagicMock()
    key.lockMac = "AA:BB:CC:DD:EE:FF"
    connection = MagicMock()
    connection.auto_lock_seconds = 15
    connection.auto_lock_limits = (5, 900)
    connection.async_set_auto_lock_time = AsyncMock()

    number = TtlockBleAutoLockTimeNumber(coordinator, key, connection)
    assert number.unique_id == "AA:BB:CC:DD:EE:FF_auto_lock_time"
    assert number.native_value == 15.0
    assert number.native_min_value == 5.0
    assert number.native_max_value == 900.0

    await number.async_set_native_value(30.0)
    connection.async_set_auto_lock_time.assert_awaited_once_with(30)

    # Test error handling
    connection.async_set_auto_lock_time.side_effect = TTLockError("BLE drop")
    with pytest.raises(HomeAssistantError):
        await number.async_set_native_value(45.0)


@pytest.mark.asyncio
async def test_auto_lock_switch_entity() -> None:
    """Test auto-lock toggle switch entity."""
    coordinator = MagicMock()
    key = MagicMock()
    key.lockMac = "AA:BB:CC:DD:EE:FF"
    connection = MagicMock()
    connection.auto_lock_seconds = 15
    connection.last_active_auto_lock = 15
    connection.auto_lock_limits = (5, 900)
    connection.async_set_auto_lock_time = AsyncMock()

    switch = TtlockBleAutoLockSwitch(coordinator, key, connection)
    assert switch.unique_id == "AA:BB:CC:DD:EE:FF_auto_lock"
    assert switch.is_on is True

    # Turn off (disables auto-lock)
    await switch.async_turn_off()
    connection.async_set_auto_lock_time.assert_awaited_once_with(0)

    # Turn on (restores last duration)
    connection.async_set_auto_lock_time.reset_mock()
    await switch.async_turn_on()
    connection.async_set_auto_lock_time.assert_awaited_once_with(15)

    # Test error handling
    connection.async_set_auto_lock_time.side_effect = TTLockError("BLE drop")
    with pytest.raises(HomeAssistantError):
        await switch.async_turn_off()


@pytest.mark.asyncio
async def test_passage_mode_switch_entity() -> None:
    """Test passage mode switch entity."""
    coordinator = MagicMock()
    key = MagicMock()
    key.lockMac = "AA:BB:CC:DD:EE:FF"
    connection = MagicMock()
    connection.passage_mode_active = True
    connection.async_set_passage_mode = AsyncMock()
    connection.async_clear_passage_mode = AsyncMock()

    switch = TtlockBlePassageModeSwitch(coordinator, key, connection)
    assert switch.unique_id == "AA:BB:CC:DD:EE:FF_passage_mode"
    assert switch.is_on is True

    # Turn off (clears passage mode)
    await switch.async_turn_off()
    connection.async_clear_passage_mode.assert_awaited_once()

    # Turn on (enables passage mode with 1-minute Monday schedule)
    await switch.async_turn_on()
    connection.async_set_passage_mode.assert_awaited_once()
    called_schedules = connection.async_set_passage_mode.call_args[0][0]
    assert len(called_schedules) == 1
    assert called_schedules[0]["week_or_day"] == 1
    assert called_schedules[0]["start_hour"] == 0
    assert called_schedules[0]["start_minute"] == 0
    assert called_schedules[0]["end_hour"] == 0
    assert called_schedules[0]["end_minute"] == 1

    # Test error handling
    connection.async_clear_passage_mode.side_effect = TTLockError("BLE drop")
    with pytest.raises(HomeAssistantError):
        await switch.async_turn_off()
