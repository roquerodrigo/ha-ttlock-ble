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
    conn.async_get_operation_log = AsyncMock(return_value=[])
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


def _advertisement(*, unlocked: bool, battery: int = 66):
    from ttlock_ble import LockAdvertisement, LockState

    return LockAdvertisement(
        protocol_type=5,
        protocol_version=3,
        scene=2,
        lock_state=LockState.UNLOCKED if unlocked else LockState.LOCKED,
        has_new_records=False,
        is_setting_mode=False,
        battery=battery,
        lock_mac="AA:BB:CC:DD:EE:FF",
    )


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
