"""Coverage for the persisted per-lock clock comparison."""

from __future__ import annotations

from custom_components.ttlock_ble.clock_sync_store import (
    STORAGE_KEY,
    STORAGE_VERSION,
    TtlockBleClockSyncStore,
)

MAC = "AA:BB:CC:DD:EE:FF"
SYNC = {"checked_at": "2026-08-29T22:00:00+00:00", "drift_seconds": -1.5}


async def test_load_tolerates_a_missing_file(hass) -> None:
    store = TtlockBleClockSyncStore(hass)
    await store.async_load()
    assert store.get(MAC) is None


async def test_load_restores_the_persisted_record(hass, hass_storage) -> None:
    hass_storage[STORAGE_KEY] = {
        "version": STORAGE_VERSION,
        "data": {MAC: SYNC},
    }
    store = TtlockBleClockSyncStore(hass)
    await store.async_load()
    assert store.get(MAC) == SYNC


async def test_remember_replaces_the_earlier_record(hass) -> None:
    store = TtlockBleClockSyncStore(hass)
    store.async_remember(MAC, SYNC)
    later = {"checked_at": "2026-08-30T22:00:00+00:00", "drift_seconds": 42.0}
    store.async_remember(MAC, later)
    assert store.get(MAC) == later


async def test_remember_writes_the_delayed_snapshot(hass, hass_storage) -> None:
    store = TtlockBleClockSyncStore(hass)
    store.async_remember(MAC, SYNC)
    await store._store.async_save(store._snapshot())
    assert hass_storage[STORAGE_KEY]["data"] == {MAC: SYNC}


async def test_locks_keep_separate_records(hass) -> None:
    store = TtlockBleClockSyncStore(hass)
    store.async_remember(MAC, SYNC)
    assert store.get("11:22:33:44:55:66") is None


async def test_every_entry_shares_one_store(hass) -> None:
    """Two instances over one storage key take turns dropping each other's writes."""
    from custom_components.ttlock_ble.clock_sync_store import async_get_clock_sync_store

    first = await async_get_clock_sync_store(hass)
    first.async_remember(MAC, SYNC)
    second = await async_get_clock_sync_store(hass)

    assert second is first
    assert second.get(MAC) == SYNC
