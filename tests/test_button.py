"""Unit tests for TTLock BLE action buttons (sync clock, sync log, refresh state)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.ttlock_ble.button import (
    TtlockBleRefreshStateButton,
    TtlockBleSyncClockButton,
    TtlockBleSyncLogButton,
    async_setup_entry,
)
from ttlock_ble import TTLockError


@pytest.mark.asyncio
async def test_button_press_sync_clock() -> None:
    """Test sync clock button press."""
    coordinator = MagicMock()
    coordinator.async_sync_clock_now = AsyncMock()
    key = MagicMock()
    key.lockMac = "AA:BB:CC:DD:EE:FF"
    connection = MagicMock()

    button = TtlockBleSyncClockButton(coordinator, key, connection)
    assert button.unique_id == "AA:BB:CC:DD:EE:FF_sync_clock"

    await button.async_press()
    coordinator.async_sync_clock_now.assert_awaited_once_with(connection)

    # Test error handling
    coordinator.async_sync_clock_now.side_effect = TTLockError("BLE drop")
    with pytest.raises(HomeAssistantError):
        await button.async_press()


@pytest.mark.asyncio
async def test_button_press_sync_log() -> None:
    """Test sync log button press."""
    coordinator = MagicMock()
    key = MagicMock()
    key.lockMac = "AA:BB:CC:DD:EE:FF"
    connection = MagicMock()
    connection.async_get_operation_log = AsyncMock()

    button = TtlockBleSyncLogButton(coordinator, key, connection)
    assert button.unique_id == "AA:BB:CC:DD:EE:FF_sync_log"

    await button.async_press()
    connection.async_get_operation_log.assert_awaited_once()

    # Test error handling
    connection.async_get_operation_log.side_effect = TTLockError("Timeout")
    with pytest.raises(HomeAssistantError):
        await button.async_press()


@pytest.mark.asyncio
async def test_button_press_refresh_state() -> None:
    """Test refresh state button press."""
    coordinator = MagicMock()
    coordinator.async_poll_lock = AsyncMock()
    key = MagicMock()
    key.lockMac = "AA:BB:CC:DD:EE:FF"
    connection = MagicMock()

    button = TtlockBleRefreshStateButton(coordinator, key, connection)
    assert button.unique_id == "AA:BB:CC:DD:EE:FF_refresh_state"

    await button.async_press()
    coordinator.async_poll_lock.assert_awaited_once_with(connection)

    # Test error handling
    coordinator.async_poll_lock.side_effect = TTLockError("Unreachable")
    with pytest.raises(HomeAssistantError):
        await button.async_press()


@pytest.mark.asyncio
async def test_async_setup_entry_buttons() -> None:
    """Test async_setup_entry creates buttons."""
    hass = MagicMock()
    entry = MagicMock()
    data = MagicMock()
    key = MagicMock()
    key.lockMac = "AA:BB:CC:DD:EE:FF"
    key.is_admin.return_value = True
    key.adminPs = "123456"

    connection = MagicMock()
    data.virtual_keys = [key]
    data.connections = {"AA:BB:CC:DD:EE:FF": connection}
    entry.runtime_data = data

    created_entities: list[object] = []

    def mock_add(entities: list[object]) -> None:
        created_entities.extend(entities)

    await async_setup_entry(hass, entry, mock_add)
    # Should create 7 buttons (sync_clock, sync_log, refresh_state, sync_passcodes, sync_cards, sync_fingerprints, sync_passage_mode)
    assert len(created_entities) == 7
