from __future__ import annotations

from homeassistant.helpers.dispatcher import async_dispatcher_send
from ttlock_ble import LockEvent

from custom_components.ttlock_ble.connection import event_signal
from custom_components.ttlock_ble.event import (
    EVENT_TYPE_FAILED,
    EVENT_TYPE_SUCCESS,
)


async def test_event_entity_created_for_each_key(hass, setup_integration) -> None:
    states = hass.states.async_all("event")
    assert len(states) == 1


async def test_event_success_fires_success_type(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    pushed = LockEvent(cmd_echo=0x47, status=1, data=b"\xaa\xbb")
    async_dispatcher_send(
        hass,
        event_signal(sample_virtual_key.lockMac),
        pushed,
    )
    await hass.async_block_till_done()
    state = hass.states.async_all("event")[0]
    assert state.attributes["event_type"] == EVENT_TYPE_SUCCESS
    assert state.attributes["cmd_echo"] == 0x47
    assert state.attributes["data"] == "aabb"


async def test_event_failure_fires_failed_type(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    pushed = LockEvent(cmd_echo=0x47, status=0, data=b"")
    async_dispatcher_send(
        hass,
        event_signal(sample_virtual_key.lockMac),
        pushed,
    )
    await hass.async_block_till_done()
    state = hass.states.async_all("event")[0]
    assert state.attributes["event_type"] == EVENT_TYPE_FAILED


async def test_event_has_unique_id(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    from homeassistant.helpers import entity_registry as er

    state = hass.states.async_all("event")[0]
    registry = er.async_get(hass)
    entry = registry.async_get(state.entity_id)
    assert entry is not None
    assert entry.unique_id == f"{sample_virtual_key.lockMac}_operation"


async def test_event_surfaces_decoded_state_push(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    """A 3-byte heartbeat push lands as attributes on the event entity."""
    pushed = LockEvent.from_payload(0x14, 1, bytes.fromhex("2c0102"))
    async_dispatcher_send(
        hass,
        event_signal(sample_virtual_key.lockMac),
        pushed,
    )
    await hass.async_block_till_done()
    attrs = hass.states.async_all("event")[0].attributes
    assert attrs["battery"] == 0x2C
    assert attrs["lock_state"] == "unlocked"
    assert "uid" not in attrs
    assert "record_id" not in attrs


async def test_event_surfaces_decoded_log_push(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    """A 15-byte log-entry push surfaces uid + record_id + timestamp."""
    payload = bytes.fromhex("2c000000006a0224a31a050b0f3008")
    pushed = LockEvent.from_payload(0x14, 1, payload)
    async_dispatcher_send(
        hass,
        event_signal(sample_virtual_key.lockMac),
        pushed,
    )
    await hass.async_block_till_done()
    attrs = hass.states.async_all("event")[0].attributes
    assert attrs["battery"] == 0x2C
    assert attrs["uid"] == 0
    assert attrs["record_id"] == 0x6A0224A3
    assert attrs["timestamp"] == "2026-05-11 15:48:08"
    assert "lock_state" not in attrs
