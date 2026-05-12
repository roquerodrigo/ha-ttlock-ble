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
    """After a successful unlock, the UI flips to `unlocked` without polling."""
    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_UNLOCK

    initial = hass.states.async_all("lock")[0]
    assert initial.state == "locked"
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


async def test_settle_window_suppresses_coordinator_flip(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    """Coordinator updates inside the post-command settle window cannot flip the UI."""
    from unittest.mock import patch

    from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
    from homeassistant.components.lock import SERVICE_UNLOCK

    # Lock's BLE state will keep returning `locked` after we just unlocked it —
    # simulates the lock lagging the mechanical state. The settle window must
    # protect the optimistic UI from bouncing.
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
        # Force a coordinator refresh while still in the settle window.
        await setup_integration.runtime_data.coordinator.async_request_refresh()
        await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == "unlocked"


async def test_lock_has_unique_id(hass, setup_integration, sample_virtual_key) -> None:
    from homeassistant.helpers import entity_registry as er

    state = hass.states.async_all("lock")[0]
    registry = er.async_get(hass)
    entry = registry.async_get(state.entity_id)
    assert entry is not None
    assert entry.unique_id == f"{sample_virtual_key.lockMac}_lock"
