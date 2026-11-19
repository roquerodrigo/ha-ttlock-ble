from __future__ import annotations

from ttlock_ble import PassageModeSlot

from custom_components.ttlock_ble.passage_mode import slot_to_record
from custom_components.ttlock_ble.switch_slot_store import (
    STORAGE_KEY,
    TtlockBleSwitchSlotStore,
    async_get_switch_slot_store,
)

MAC = "AA:BB:CC:DD:EE:FF"
SLOT = PassageModeSlot(kind=1, day=6, month=0, start_minute=0, end_minute=1440)


async def test_load_tolerates_a_missing_file(hass) -> None:
    store = TtlockBleSwitchSlotStore(hass)
    await store.async_load()
    assert store.get(MAC) == []


async def test_load_restores_the_persisted_slots(hass, hass_storage) -> None:
    hass_storage[STORAGE_KEY] = {"version": 1, "data": {MAC: [slot_to_record(SLOT)]}}
    store = TtlockBleSwitchSlotStore(hass)
    await store.async_load()
    assert store.get(MAC) == [SLOT]


async def test_remember_is_written_at_once(hass, hass_storage) -> None:
    """A record lost in a crash seconds after the write is the case this is for."""
    store = TtlockBleSwitchSlotStore(hass)
    await store.async_remember(MAC, [SLOT])
    assert hass_storage[STORAGE_KEY]["data"] == {MAC: [slot_to_record(SLOT)]}


async def test_remembering_nothing_forgets(hass, hass_storage) -> None:
    store = TtlockBleSwitchSlotStore(hass)
    await store.async_remember(MAC, [SLOT])
    await store.async_remember(MAC, [])
    assert store.get(MAC) == []
    assert hass_storage[STORAGE_KEY]["data"] == {}


async def test_forgetting_an_unknown_lock_writes_nothing(hass, hass_storage) -> None:
    store = TtlockBleSwitchSlotStore(hass)
    await store.async_forget(MAC)
    assert STORAGE_KEY not in hass_storage


async def test_one_store_is_shared_per_instance(hass) -> None:
    assert await async_get_switch_slot_store(hass) is await async_get_switch_slot_store(
        hass
    )
