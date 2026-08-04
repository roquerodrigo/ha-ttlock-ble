from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError
from ttlock_ble import TTLockError


async def test_lock_entity_created_for_each_key(hass, setup_integration) -> None:
    assert len(hass.states.async_all("lock")) == 1


async def test_lock_state_locked(hass, setup_integration) -> None:
    # default mock_ttlock_connection returns (0, 80) -> locked
    states = hass.states.async_all("lock")
    assert states[0].state == "locked"


async def test_lock_state_unlocked(
    hass,
    sample_virtual_key,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    mock_ttlock_connection.async_query_state = AsyncMock(return_value=(1, 80))
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "username": "u",
            "password": "p",
            "keys": [sample_stored_key],
        },
        unique_id="u",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    states = hass.states.async_all("lock")
    assert states[0].state == "unlocked"


async def test_async_lock_calls_connection(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_LOCK

    state = hass.states.async_all("lock")[0]
    await hass.services.async_call(
        LOCK_DOMAIN,
        SERVICE_LOCK,
        {"entity_id": state.entity_id},
        blocking=True,
    )
    mock_ttlock_connection.async_lock.assert_awaited_once()


async def test_async_unlock_calls_connection(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_UNLOCK

    state = hass.states.async_all("lock")[0]
    await hass.services.async_call(
        LOCK_DOMAIN,
        SERVICE_UNLOCK,
        {"entity_id": state.entity_id},
        blocking=True,
    )
    mock_ttlock_connection.async_unlock.assert_awaited_once()


async def test_async_lock_wraps_ttlock_error(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_LOCK

    mock_ttlock_connection.async_lock = AsyncMock(side_effect=TTLockError("offline"))
    state = hass.states.async_all("lock")[0]
    with pytest.raises(HomeAssistantError, match="Failed to lock"):
        await hass.services.async_call(
            LOCK_DOMAIN,
            SERVICE_LOCK,
            {"entity_id": state.entity_id},
            blocking=True,
        )


async def test_async_unlock_wraps_ttlock_error(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_UNLOCK

    mock_ttlock_connection.async_unlock = AsyncMock(
        side_effect=TTLockError("ble timeout")
    )
    state = hass.states.async_all("lock")[0]
    with pytest.raises(HomeAssistantError, match="Failed to unlock"):
        await hass.services.async_call(
            LOCK_DOMAIN,
            SERVICE_UNLOCK,
            {"entity_id": state.entity_id},
            blocking=True,
        )


async def test_async_unlock_sets_optimistic_state(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    """After a successful unlock, the UI flips to `unlocked` without a refresh."""
    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_UNLOCK

    initial = hass.states.async_all("lock")[0]
    assert initial.state == "locked"
    # The post-command refresh finds the lock out of range.
    mock_ttlock_connection.async_query_state = AsyncMock(return_value=None)
    await hass.services.async_call(
        LOCK_DOMAIN,
        SERVICE_UNLOCK,
        {"entity_id": initial.entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    after = hass.states.get(initial.entity_id)
    assert after is not None
    assert after.state == "unlocked"


async def test_async_lock_sets_optimistic_state(
    hass,
    sample_virtual_key,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    """After a successful lock command the entity reports `locked`."""
    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_LOCK
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    # Start with the coordinator reporting "unlocked", then issue lock and check.
    mock_ttlock_connection.async_query_state = AsyncMock(return_value=(1, 80))
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "u", "password": "p", "keys": [sample_stored_key]},
        unique_id="u",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.async_all("lock")[0]
    assert state.state == "unlocked"
    # The post-command refresh finds the lock out of range.
    mock_ttlock_connection.async_query_state = AsyncMock(return_value=None)
    await hass.services.async_call(
        LOCK_DOMAIN,
        SERVICE_LOCK,
        {"entity_id": state.entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    after = hass.states.get(state.entity_id)
    assert after is not None
    assert after.state == "locked"


async def test_settle_window_suppresses_blink(
    hass,
    setup_integration,
    mock_ttlock_connection,
    sample_virtual_key,
) -> None:
    """Force-queries inside the post-command settle window cannot flip the UI."""
    from unittest.mock import patch

    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_UNLOCK
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    from ttlock_ble import LockEvent

    from custom_components.ttlock_ble.connection import event_signal

    # The mock returns "locked" — simulates the lock's BLE state lagging the
    # mechanical unlock. With settle active, this must NOT bounce the UI.
    mock_ttlock_connection.async_query_state = AsyncMock(return_value=(0, 80))
    state = hass.states.async_all("lock")[0]
    assert state.state == "locked"
    with patch("custom_components.ttlock_ble.lock.COMMAND_SETTLE_SECONDS", 60.0):
        await hass.services.async_call(
            LOCK_DOMAIN,
            SERVICE_UNLOCK,
            {"entity_id": state.entity_id},
            blocking=True,
        )
        # Drive a push event while still in the settle window; the lock entity
        # force-queries (returning "locked") but must NOT flip the UI.
        async_dispatcher_send(
            hass,
            event_signal(sample_virtual_key.lockMac),
            LockEvent(cmd_echo=0x14, status=1, data=b""),
        )
        await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == "unlocked"


async def test_lock_event_triggers_state_refresh(
    hass,
    setup_integration,
    mock_ttlock_connection,
    sample_virtual_key,
) -> None:
    """A push event on the dispatcher signal forces a state re-query."""
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    from ttlock_ble import LockEvent

    from custom_components.ttlock_ble.connection import event_signal

    state = hass.states.async_all("lock")[0]
    assert state.state == "locked"
    # Pretend the lock just got unlocked by a keypad press.
    mock_ttlock_connection.async_query_state = AsyncMock(return_value=(1, 80))
    async_dispatcher_send(
        hass,
        event_signal(sample_virtual_key.lockMac),
        LockEvent(cmd_echo=0x47, status=1, data=b""),
    )
    await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == "unlocked"
    mock_ttlock_connection.async_query_state.assert_awaited()


async def test_lock_event_with_decoded_state_skips_query(
    hass,
    setup_integration,
    mock_ttlock_connection,
    sample_virtual_key,
) -> None:
    """A push event carrying `lock_state` updates the UI without re-querying."""
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    from ttlock_ble import LockEvent

    from custom_components.ttlock_ble.connection import event_signal

    state = hass.states.async_all("lock")[0]
    assert state.state == "locked"
    mock_ttlock_connection.async_query_state = AsyncMock(
        side_effect=AssertionError("must not be called when lock_state is decoded")
    )
    async_dispatcher_send(
        hass,
        event_signal(sample_virtual_key.lockMac),
        LockEvent.from_payload(0x14, 1, bytes([0x2C, 0x01, 0x02])),
    )
    await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == "unlocked"
    mock_ttlock_connection.async_query_state.assert_not_awaited()


async def test_lock_event_with_decoded_state_respects_settle_window(
    hass,
    setup_integration,
    mock_ttlock_connection,
    sample_virtual_key,
) -> None:
    """A decoded-state push that disagrees with a just-commanded state is suppressed."""
    from unittest.mock import patch

    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_UNLOCK
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    from ttlock_ble import LockEvent

    from custom_components.ttlock_ble.connection import event_signal

    mock_ttlock_connection.async_query_state = AsyncMock(return_value=None)
    state = hass.states.async_all("lock")[0]
    assert state.state == "locked"
    with patch("custom_components.ttlock_ble.lock.COMMAND_SETTLE_SECONDS", 60.0):
        await hass.services.async_call(
            LOCK_DOMAIN,
            SERVICE_UNLOCK,
            {"entity_id": state.entity_id},
            blocking=True,
        )
        # Lock's BLE state still says "locked" (lock_state=0) right after the
        # unlock command. The settle window must suppress this flip.
        async_dispatcher_send(
            hass,
            event_signal(sample_virtual_key.lockMac),
            LockEvent.from_payload(0x14, 1, bytes([0x2C, 0x00, 0x02])),
        )
        await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == "unlocked"


async def test_unlock_reports_unlocking_while_in_flight(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    """The entity sits on `unlocking` for as long as the BLE command runs."""
    import asyncio

    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_UNLOCK

    started = asyncio.Event()
    released = asyncio.Event()

    async def blocking_unlock() -> None:
        started.set()
        await released.wait()

    mock_ttlock_connection.async_unlock = AsyncMock(side_effect=blocking_unlock)
    state = hass.states.async_all("lock")[0]
    assert state.state == "locked"
    # The post-command refresh finds the lock out of range.
    mock_ttlock_connection.async_query_state = AsyncMock(return_value=None)
    call = hass.async_create_task(
        hass.services.async_call(
            LOCK_DOMAIN,
            SERVICE_UNLOCK,
            {"entity_id": state.entity_id},
            blocking=True,
        )
    )
    async with asyncio.timeout(5):
        await started.wait()
    assert hass.states.get(state.entity_id).state == "unlocking"
    released.set()
    await call
    await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == "unlocked"


async def test_lock_reports_locking_while_in_flight(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    """The entity sits on `locking` for as long as the BLE command runs."""
    import asyncio

    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_LOCK

    started = asyncio.Event()
    released = asyncio.Event()

    async def blocking_lock() -> None:
        started.set()
        await released.wait()

    mock_ttlock_connection.async_lock = AsyncMock(side_effect=blocking_lock)
    # The post-command refresh finds the lock out of range.
    mock_ttlock_connection.async_query_state = AsyncMock(return_value=None)
    state = hass.states.async_all("lock")[0]
    call = hass.async_create_task(
        hass.services.async_call(
            LOCK_DOMAIN,
            SERVICE_LOCK,
            {"entity_id": state.entity_id},
            blocking=True,
        )
    )
    async with asyncio.timeout(5):
        await started.wait()
    assert hass.states.get(state.entity_id).state == "locking"
    released.set()
    await call
    await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == "locked"


async def test_failed_command_clears_transitional_state(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    """A rejected command drops `unlocking` instead of stranding the UI on it."""
    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_UNLOCK

    mock_ttlock_connection.async_unlock = AsyncMock(side_effect=TTLockError("offline"))
    state = hass.states.async_all("lock")[0]
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            LOCK_DOMAIN,
            SERVICE_UNLOCK,
            {"entity_id": state.entity_id},
            blocking=True,
        )
    await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == "locked"


async def test_successful_command_reads_the_operation_log(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    """The record the lock writes for our own command has to be picked up."""
    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_UNLOCK

    # The coordinator's own poll reads the log too, so silence that leg —
    # otherwise this passes even with the post-command fetch deleted.
    mock_ttlock_connection.async_query_state = AsyncMock(return_value=None)
    mock_ttlock_connection.async_get_operation_log.reset_mock()
    state = hass.states.async_all("lock")[0]
    await hass.services.async_call(
        LOCK_DOMAIN, SERVICE_UNLOCK, {"entity_id": state.entity_id}, blocking=True
    )
    await hass.async_block_till_done()
    mock_ttlock_connection.async_get_operation_log.assert_awaited()


async def test_failed_command_does_not_read_the_operation_log(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    """Nothing was executed, so there is no new record to go looking for."""
    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_UNLOCK

    mock_ttlock_connection.async_unlock = AsyncMock(side_effect=TTLockError("offline"))
    mock_ttlock_connection.async_query_state = AsyncMock(return_value=None)
    mock_ttlock_connection.async_get_operation_log.reset_mock()
    state = hass.states.async_all("lock")[0]
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            LOCK_DOMAIN, SERVICE_UNLOCK, {"entity_id": state.entity_id}, blocking=True
        )
    await hass.async_block_till_done()
    mock_ttlock_connection.async_get_operation_log.assert_not_awaited()


async def test_concurrent_commands_do_not_erase_each_others_state(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    """A second command cannot publish a settled state while the first still runs."""
    import asyncio

    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_LOCK, SERVICE_UNLOCK

    unlock_started = asyncio.Event()
    release_unlock = asyncio.Event()

    async def blocking_unlock() -> None:
        unlock_started.set()
        await release_unlock.wait()

    mock_ttlock_connection.async_unlock = AsyncMock(side_effect=blocking_unlock)
    mock_ttlock_connection.async_query_state = AsyncMock(return_value=None)
    state = hass.states.async_all("lock")[0]
    unlock_call = hass.async_create_task(
        hass.services.async_call(
            LOCK_DOMAIN, SERVICE_UNLOCK, {"entity_id": state.entity_id}, blocking=True
        )
    )
    async with asyncio.timeout(5):
        await unlock_started.wait()
    lock_call = hass.async_create_task(
        hass.services.async_call(
            LOCK_DOMAIN, SERVICE_LOCK, {"entity_id": state.entity_id}, blocking=True
        )
    )
    await asyncio.sleep(0)
    # The lock command must be queued behind the running unlock, not resolve
    # ahead of it and publish "locked" while the bolt is still moving.
    assert hass.states.get(state.entity_id).state == "unlocking"
    release_unlock.set()
    await unlock_call
    await lock_call
    await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == "locked"
    mock_ttlock_connection.async_lock.assert_awaited_once()


async def test_cancelled_command_clears_transitional_state(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    """A cancelled command must not strand the entity on `unlocking`."""
    import asyncio

    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_UNLOCK

    started = asyncio.Event()

    async def never_returns() -> None:
        started.set()
        await asyncio.Event().wait()

    mock_ttlock_connection.async_unlock = AsyncMock(side_effect=never_returns)
    state = hass.states.async_all("lock")[0]
    call = hass.async_create_task(
        hass.services.async_call(
            LOCK_DOMAIN,
            SERVICE_UNLOCK,
            {"entity_id": state.entity_id},
            blocking=True,
        )
    )
    async with asyncio.timeout(5):
        await started.wait()
    assert hass.states.get(state.entity_id).state == "unlocking"
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == "locked"


async def test_non_ttlock_error_clears_transitional_state(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    """A BleakError-style escape is wrapped and does not strand the entity."""
    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_UNLOCK

    mock_ttlock_connection.async_unlock = AsyncMock(
        side_effect=RuntimeError("checkUserTime FAILED: status=0x0")
    )
    state = hass.states.async_all("lock")[0]
    with pytest.raises(RuntimeError):
        await hass.services.async_call(
            LOCK_DOMAIN,
            SERVICE_UNLOCK,
            {"entity_id": state.entity_id},
            blocking=True,
        )
    await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == "locked"


async def test_lock_never_reports_jammed_or_open(hass, setup_integration) -> None:
    """The firmware has no jam or latch signal, so those stay unreported."""
    from homeassistant.components.lock import DATA_COMPONENT

    state = hass.states.async_all("lock")[0]
    entity = hass.data[DATA_COMPONENT].get_entity(state.entity_id)
    assert entity is not None
    assert entity.is_jammed is None
    assert entity.is_open is None
    assert entity.is_opening is None


async def test_lock_has_unique_id(hass, setup_integration, sample_virtual_key) -> None:
    from homeassistant.helpers import entity_registry as er

    state = hass.states.async_all("lock")[0]
    registry = er.async_get(hass)
    entry = registry.async_get(state.entity_id)
    assert entry is not None
    assert entry.unique_id == f"{sample_virtual_key.lockMac}_lock"


async def test_push_with_an_undecodable_state_byte_falls_back_to_a_query(
    hass,
    setup_integration,
    mock_ttlock_connection,
    sample_virtual_key,
) -> None:
    """Build the event through the SDK, so the shape asserted is one it emits."""
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    from ttlock_ble import LockEvent

    from custom_components.ttlock_ble.connection import event_signal

    # A state byte outside the two the firmware defines decodes to None,
    # which is the only "unknown" the entity can ever be handed.
    event = LockEvent.from_payload(0x14, 1, bytes([0x2C, 0x02, 0x00]))
    assert event.lock_state is None

    state = hass.states.async_all("lock")[0]
    assert state.state == "locked"
    mock_ttlock_connection.async_query_state = AsyncMock(return_value=(1, 80))
    async_dispatcher_send(hass, event_signal(sample_virtual_key.lockMac), event)
    await hass.async_block_till_done()
    mock_ttlock_connection.async_query_state.assert_awaited()
    assert hass.states.get(state.entity_id).state == "unlocked"


async def test_lock_event_forced_query_returns_none_keeps_state(
    hass,
    setup_integration,
    mock_ttlock_connection,
    sample_virtual_key,
) -> None:
    """When the forced re-query yields no state, the UI keeps its last value."""
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    from ttlock_ble import LockEvent

    from custom_components.ttlock_ble.connection import event_signal

    state = hass.states.async_all("lock")[0]
    assert state.state == "locked"
    mock_ttlock_connection.async_query_state = AsyncMock(return_value=None)
    async_dispatcher_send(
        hass,
        event_signal(sample_virtual_key.lockMac),
        LockEvent(cmd_echo=0x47, status=1, data=b""),
    )
    await hass.async_block_till_done()
    mock_ttlock_connection.async_query_state.assert_awaited()
    assert hass.states.get(state.entity_id).state == "locked"


def test_lock_sync_from_coordinator_no_snapshot_keeps_state(
    hass,
    sample_virtual_key,
) -> None:
    """An empty coordinator snapshot leaves `_attr_is_locked` untouched."""
    from datetime import timedelta
    from unittest.mock import MagicMock

    from custom_components.ttlock_ble.coordinator import TtlockBleDataUpdateCoordinator
    from custom_components.ttlock_ble.lock import TtlockBleLock

    coordinator = TtlockBleDataUpdateCoordinator(
        hass,
        timedelta(seconds=30),
        {},
    )
    coordinator.data = {}
    entity = TtlockBleLock(coordinator, sample_virtual_key, MagicMock())
    assert entity.is_locked is None
    entity._attr_is_locked = True
    entity._sync_from_coordinator()
    assert entity.is_locked is True
