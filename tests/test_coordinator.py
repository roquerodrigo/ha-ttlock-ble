from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ttlock_ble.coordinator import (
    TtlockBleDataUpdateCoordinator,
    _parse_lock_state,
)


def test_parse_lock_state_locked() -> None:
    assert _parse_lock_state(0) is True


def test_parse_lock_state_unlocked() -> None:
    assert _parse_lock_state(1) is False


@pytest.mark.parametrize("raw_state", [-1, 2, 9])
def test_parse_lock_state_unknown(raw_state: int) -> None:
    assert _parse_lock_state(raw_state) is None


def _mock_connection(*, query_return=(0, 80)) -> MagicMock:
    conn = MagicMock()
    conn.async_query_state = AsyncMock(return_value=query_return)
    return conn


def _coordinator(hass, connections):
    return TtlockBleDataUpdateCoordinator(
        hass=hass,
        scan_interval=timedelta(seconds=60),
        connections=connections,
    )


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
    assert state["available"] is True


async def test_coordinator_polls_state_unlocked(hass, sample_virtual_key) -> None:
    conn = _mock_connection(query_return=(1, 60))
    coordinator = _coordinator(hass, {sample_virtual_key.lockMac: conn})
    data = await coordinator._async_update_data()
    assert data[sample_virtual_key.lockMac]["locked"] is False


async def test_coordinator_marks_unavailable_when_query_returns_none(
    hass,
    sample_virtual_key,
) -> None:
    conn = _mock_connection(query_return=None)
    coordinator = _coordinator(hass, {sample_virtual_key.lockMac: conn})
    data = await coordinator._async_update_data()
    state = data[sample_virtual_key.lockMac]
    assert state["available"] is False
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
