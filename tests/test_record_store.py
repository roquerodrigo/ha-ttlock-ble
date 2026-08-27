"""Coverage for the persisted operation-log cursor."""

from __future__ import annotations

from custom_components.ttlock_ble.record_store import (
    MAX_RECORDS_PER_LOCK,
    STORAGE_KEY,
    STORAGE_VERSION,
    TtlockBleRecordStore,
)

MAC = "AA:BB:CC:DD:EE:FF"


async def test_load_tolerates_a_missing_file(hass) -> None:
    store = TtlockBleRecordStore(hass)
    await store.async_load()
    assert store.seen(MAC) == set()


async def test_load_restores_the_persisted_ids(hass, hass_storage) -> None:
    hass_storage[STORAGE_KEY] = {
        "version": STORAGE_VERSION,
        "data": {MAC: {"seeded": True, "records": [7, 8, 9]}},
    }
    store = TtlockBleRecordStore(hass)
    await store.async_load()
    assert store.seen(MAC) == {7, 8, 9}


async def test_seen_hands_back_a_copy(hass) -> None:
    """A caller mutating its own set must not silently move the cursor."""
    store = TtlockBleRecordStore(hass)
    store.async_remember(MAC, {1, 2})
    borrowed = store.seen(MAC)
    borrowed.add(3)
    assert store.seen(MAC) == {1, 2}


async def test_remember_keeps_only_the_most_recent_ids(hass) -> None:
    store = TtlockBleRecordStore(hass)
    store.async_remember(MAC, set(range(MAX_RECORDS_PER_LOCK * 2)))
    kept = store.seen(MAC)
    assert len(kept) == MAX_RECORDS_PER_LOCK
    assert max(kept) == MAX_RECORDS_PER_LOCK * 2 - 1


async def test_remember_writes_the_delayed_snapshot(hass, hass_storage) -> None:
    store = TtlockBleRecordStore(hass)
    store.async_remember(MAC, {3, 1, 2})
    await store._store.async_save(store._snapshot())
    assert hass_storage[STORAGE_KEY]["data"] == {
        MAC: {"seeded": True, "records": [1, 2, 3]}
    }


async def test_locks_keep_separate_cursors(hass) -> None:
    other = "11:22:33:44:55:66"
    store = TtlockBleRecordStore(hass)
    store.async_remember(MAC, {1})
    store.async_remember(other, {2})
    assert store.seen(MAC) == {1}
    assert store.seen(other) == {2}


async def test_a_lock_is_not_seeded_until_it_is_remembered(hass) -> None:
    store = TtlockBleRecordStore(hass)
    assert store.is_seeded(MAC) is False
    store.async_remember(MAC, set())
    assert store.is_seeded(MAC) is True


async def test_an_empty_backlog_still_marks_the_lock_seeded(hass, hass_storage) -> None:
    """A lock whose log was already synced seeds nothing, and must not seed twice."""
    store = TtlockBleRecordStore(hass)
    store.async_remember(MAC, set())
    await store._store.async_save(store._snapshot())

    restored = TtlockBleRecordStore(hass)
    await restored.async_load()
    assert restored.seen(MAC) == set()
    assert restored.is_seeded(MAC) is True


async def test_every_entry_shares_one_store(hass) -> None:
    """Two instances over one storage key take turns dropping each other's writes."""
    from custom_components.ttlock_ble.record_store import async_get_record_store

    first = await async_get_record_store(hass)
    first.async_remember(MAC, {1, 2})
    second = await async_get_record_store(hass)

    assert second is first
    assert second.seen(MAC) == {1, 2}
