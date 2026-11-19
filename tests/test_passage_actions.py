from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from ttlock_ble import PassageModeSlot, TTLockError

from custom_components.ttlock_ble.const import DOMAIN
from custom_components.ttlock_ble.passage_mode import always_slots
from custom_components.ttlock_ble.switch_slot_store import async_get_switch_slot_store

MAC = "AA:BB:CC:DD:EE:FF"


def _lock_id(hass) -> str:
    return hass.states.async_all("lock")[0].entity_id


async def _call(hass, service: str, **data: object) -> None:
    await hass.services.async_call(
        DOMAIN,
        service,
        {"entity_id": _lock_id(hass), **data},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_set_passage_mode_writes_the_schedule_next_to_the_existing_slots(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    """Replacing what the lock holds has to be asked for."""
    await _call(
        hass,
        "set_passage_mode",
        start_time="09:00:00",
        end_time="17:30:00",
        days=["mon", "wed"],
    )

    mock_ttlock_connection.async_clear_passage_slots.assert_not_awaited()
    slots = [
        call.args[0]
        for call in mock_ttlock_connection.async_add_passage_slot.await_args_list
    ]
    assert [(s.day, s.start_minute, s.end_minute) for s in slots] == [
        (1, 540, 1050),
        (3, 540, 1050),
    ]
    mock_ttlock_connection.async_get_passage_slots.assert_awaited()


async def test_set_passage_mode_defaults_to_every_day(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    await _call(hass, "set_passage_mode", start_time="09:00:00", end_time="17:00:00")

    assert mock_ttlock_connection.async_add_passage_slot.await_count == 7


async def test_set_passage_mode_can_replace_the_existing_slots(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    store = await async_get_switch_slot_store(hass)
    await store.async_remember(MAC, always_slots())

    await _call(
        hass,
        "set_passage_mode",
        start_time="09:00:00",
        end_time="10:00:00",
        days=["fri"],
        clear_existing=True,
    )

    mock_ttlock_connection.async_clear_passage_slots.assert_awaited_once()
    assert store.get(MAC) == []


async def test_a_schedule_that_does_not_end_after_it_starts_sends_nothing(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    with pytest.raises(ServiceValidationError):
        await _call(
            hass, "set_passage_mode", start_time="17:00:00", end_time="09:00:00"
        )

    mock_ttlock_connection.async_add_passage_slot.assert_not_awaited()


@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("get_passage_mode", {}),
        ("clear_passage_mode", {}),
        ("set_passage_mode", {"start_time": "09:00:00", "end_time": "10:00:00"}),
    ],
)
async def test_a_lock_that_cannot_be_asked_is_refused_before_anything_is_sent(
    hass,
    setup_integration,
    mock_ttlock_connection,
    service,
    data,
) -> None:
    async def _call_it() -> None:
        if service == "get_passage_mode":
            await hass.services.async_call(
                DOMAIN,
                service,
                {"entity_id": _lock_id(hass)},
                blocking=True,
                return_response=True,
            )
        else:
            await _call(hass, service, **data)

    with (
        patch(
            "custom_components.ttlock_ble.lock.can_manage_passage_mode",
            return_value=False,
        ),
        pytest.raises(ServiceValidationError),
    ):
        await _call_it()

    mock_ttlock_connection.async_get_passage_slots.assert_not_awaited()
    mock_ttlock_connection.async_add_passage_slot.assert_not_awaited()
    mock_ttlock_connection.async_clear_passage_slots.assert_not_awaited()


async def test_a_refused_schedule_surfaces_and_rereads_the_lock(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    mock_ttlock_connection.async_add_passage_slot.side_effect = TTLockError("refused")

    with pytest.raises(HomeAssistantError):
        await _call(
            hass, "set_passage_mode", start_time="09:00:00", end_time="10:00:00"
        )

    mock_ttlock_connection.async_get_passage_slots.assert_awaited()


async def test_get_passage_mode_returns_the_slots(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    mock_ttlock_connection.async_get_passage_slots.return_value = [
        PassageModeSlot(kind=1, day=6, month=0, start_minute=1335, end_minute=1440)
    ]
    entity_id = _lock_id(hass)

    response = await hass.services.async_call(
        DOMAIN,
        "get_passage_mode",
        {"entity_id": entity_id},
        blocking=True,
        return_response=True,
    )

    assert response[entity_id] == {
        "slots": [{"kind": 1, "day": 6, "month": 0, "start": "22:15", "end": "24:00"}]
    }
    coordinator = setup_integration.runtime_data.coordinator
    assert len(coordinator.async_passage_slots(MAC)) == 1


async def test_clear_passage_mode_clears_the_lock_and_forgets_the_switch_slots(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    store = await async_get_switch_slot_store(hass)
    await store.async_remember(MAC, always_slots())

    await _call(hass, "clear_passage_mode")

    mock_ttlock_connection.async_clear_passage_slots.assert_awaited_once()
    assert store.get(MAC) == []
    coordinator = setup_integration.runtime_data.coordinator
    assert coordinator.async_passage_slots(MAC) == []


async def test_passage_mode_failures_surface(
    hass,
    setup_integration,
    mock_ttlock_connection,
) -> None:
    mock_ttlock_connection.async_get_passage_slots.side_effect = TTLockError("x")
    mock_ttlock_connection.async_clear_passage_slots.side_effect = TTLockError("x")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "get_passage_mode",
            {"entity_id": _lock_id(hass)},
            blocking=True,
            return_response=True,
        )
    with pytest.raises(HomeAssistantError):
        await _call(hass, "clear_passage_mode")
