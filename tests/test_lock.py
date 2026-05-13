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
    # Simulate cooldown for the post-command refresh.
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
    # Simulate cooldown for the post-command refresh.
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
    mock_ttlock_connection.async_query_state.assert_awaited_with(
        force_cooldown_bypass=True
    )


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
        LockEvent(cmd_echo=0x14, status=1, data=b"\x2c\x01\x02", lock_state=1),
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
            LockEvent(cmd_echo=0x14, status=1, data=b"\x2c\x00\x02", lock_state=0),
        )
        await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == "unlocked"


async def test_lock_has_unique_id(hass, setup_integration, sample_virtual_key) -> None:
    from homeassistant.helpers import entity_registry as er

    state = hass.states.async_all("lock")[0]
    registry = er.async_get(hass)
    entry = registry.async_get(state.entity_id)
    assert entry is not None
    assert entry.unique_id == f"{sample_virtual_key.lockMac}_lock"
