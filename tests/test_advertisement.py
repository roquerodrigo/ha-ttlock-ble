"""Coverage for the passive advertisement tracker."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

MAC = "AA:BB:CC:DD:EE:FF"
MAC_TAIL = bytes.fromhex("ffeeddccbbaa")
V3_COMPANY_ID = 0x0305


def manufacturer_data(flags: int, battery: int = 77, tail: bytes = MAC_TAIL) -> dict:
    """Build the `manufacturer_data` mapping of a protocol 5.3 advertisement."""
    return {V3_COMPANY_ID: bytes([2, flags, battery, 0, 0, 0, 0]) + tail}


def service_info(data: dict) -> MagicMock:
    """Stand-in for the `BluetoothServiceInfoBleak` HA hands to the callback."""
    info = MagicMock(name="BluetoothServiceInfoBleak")
    info.address = MAC
    info.manufacturer_data = data
    return info


@pytest.fixture
def tracker(hass):
    from custom_components.ttlock_ble.advertisement import (
        TtlockBleAdvertisementTracker,
    )

    coordinator = MagicMock(name="Coordinator")
    coordinator.async_request_refresh = AsyncMock(return_value=None)
    coordinator.async_has_state = MagicMock(return_value=False)
    return TtlockBleAdvertisementTracker(hass, coordinator), coordinator


async def test_register_subscribes_once_per_lock(hass, sample_virtual_key) -> None:
    from custom_components.ttlock_ble.advertisement import (
        TtlockBleAdvertisementTracker,
    )

    with patch(
        "custom_components.ttlock_ble.advertisement.async_register_callback",
        return_value=MagicMock(),
    ) as register:
        unsubs = TtlockBleAdvertisementTracker(hass, MagicMock()).async_register(
            [sample_virtual_key],
        )
    assert len(unsubs) == 1
    matcher = register.call_args.args[2]
    assert matcher["address"] == sample_virtual_key.lockMac


async def test_unlocked_advertisement_updates_the_coordinator(tracker) -> None:
    instance, coordinator = tracker
    instance._async_on_advertisement(MAC, service_info(manufacturer_data(0x01)), None)
    coordinator.async_apply_advertisement.assert_called_once()
    mac, advertisement = coordinator.async_apply_advertisement.call_args.args
    assert mac == MAC
    assert advertisement.lock_state == 1
    assert advertisement.battery == 77
    coordinator.async_request_refresh.assert_not_called()


async def test_locked_advertisement_updates_the_coordinator(tracker) -> None:
    instance, coordinator = tracker
    instance._async_on_advertisement(MAC, service_info(manufacturer_data(0x00)), None)
    _mac, advertisement = coordinator.async_apply_advertisement.call_args.args
    assert advertisement.lock_state == 0


async def test_payload_for_another_address_is_ignored(tracker, hass) -> None:
    instance, coordinator = tracker
    other_tail = bytes.fromhex("112233445566")
    instance._async_on_advertisement(
        MAC,
        service_info(manufacturer_data(0x01, tail=other_tail)),
        None,
    )
    await hass.async_block_till_done()
    coordinator.async_apply_advertisement.assert_not_called()


async def test_undecodable_advertisement_falls_back_to_a_poll(tracker, hass) -> None:
    instance, coordinator = tracker
    instance._async_on_advertisement(MAC, service_info({0x004C: b"\x02\x15"}), None)
    await hass.async_block_till_done()
    coordinator.async_apply_advertisement.assert_not_called()
    coordinator.async_request_refresh.assert_awaited_once()


async def test_undecodable_advertisement_does_not_poll_once_state_is_known(
    tracker,
    hass,
) -> None:
    """The bootstrap poll is for the first reading only, never a per-advert refresh."""
    instance, coordinator = tracker
    coordinator.async_has_state = MagicMock(return_value=True)
    instance._async_on_advertisement(MAC, service_info({0x004C: b"\x02\x15"}), None)
    await hass.async_block_till_done()
    coordinator.async_request_refresh.assert_not_awaited()
