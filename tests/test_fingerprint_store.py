"""Coverage for the persisted fingerprint list and names."""

from __future__ import annotations

from custom_components.ttlock_ble.data import TtlockBleEnrolledFingerprint
from custom_components.ttlock_ble.fingerprint_store import (
    STORAGE_KEY,
    STORAGE_VERSION,
    TtlockBleFingerprintStore,
)

MAC = "AA:BB:CC:DD:EE:FF"
THUMB = TtlockBleEnrolledFingerprint(fingerprint_id=bytes.fromhex("0000002a"), slot=1)
INDEX = TtlockBleEnrolledFingerprint(fingerprint_id=bytes.fromhex("0000002b"), slot=2)


async def test_load_tolerates_a_missing_file(hass) -> None:
    store = TtlockBleFingerprintStore(hass)
    await store.async_load()
    assert store.enrolled(MAC) is None


async def test_load_restores_the_list_and_its_names(hass, hass_storage) -> None:
    hass_storage[STORAGE_KEY] = {
        "version": STORAGE_VERSION,
        "data": {MAC: {THUMB.token: "Alice", INDEX.token: ""}},
    }
    store = TtlockBleFingerprintStore(hass)
    await store.async_load()

    assert store.enrolled(MAC) == [THUMB, INDEX]
    assert store.name_of(MAC, THUMB) == "Alice"
    assert store.name_of(MAC, INDEX) is None


async def test_a_stored_token_that_is_no_fingerprint_is_skipped(
    hass, hass_storage
) -> None:
    hass_storage[STORAGE_KEY] = {
        "version": STORAGE_VERSION,
        "data": {MAC: {"not-a-token": "Bob", THUMB.token: ""}},
    }
    store = TtlockBleFingerprintStore(hass)
    await store.async_load()

    assert store.enrolled(MAC) == [THUMB]


async def test_the_list_is_sorted_by_number(hass) -> None:
    store = TtlockBleFingerprintStore(hass)
    store.async_replace(MAC, {INDEX, THUMB})

    assert store.enrolled(MAC) == [THUMB, INDEX]


async def test_a_name_survives_a_new_read_of_the_same_fingerprint(hass) -> None:
    store = TtlockBleFingerprintStore(hass)
    store.async_replace(MAC, {THUMB})
    store.async_set_name(MAC, THUMB, "  Alice ")
    store.async_replace(MAC, {THUMB, INDEX})

    assert store.name_of(MAC, THUMB) == "Alice"
    assert store.name_of(MAC, INDEX) is None


async def test_a_fingerprint_the_lock_dropped_takes_its_name_with_it(hass) -> None:
    store = TtlockBleFingerprintStore(hass)
    store.async_replace(MAC, {THUMB})
    store.async_set_name(MAC, THUMB, "Alice")
    store.async_replace(MAC, set())
    store.async_replace(MAC, {THUMB})

    assert store.enrolled(MAC) == [THUMB]
    assert store.name_of(MAC, THUMB) is None


async def test_an_empty_name_clears_the_one_given(hass) -> None:
    store = TtlockBleFingerprintStore(hass)
    store.async_replace(MAC, {THUMB})
    store.async_set_name(MAC, THUMB, "Alice")
    store.async_set_name(MAC, THUMB, "   ")

    assert store.name_of(MAC, THUMB) is None


async def test_an_unchanged_list_schedules_no_write(hass) -> None:
    from unittest.mock import patch

    store = TtlockBleFingerprintStore(hass)
    store.async_replace(MAC, {THUMB})

    with patch.object(store._store, "async_delay_save") as delay_save:
        store.async_replace(MAC, {THUMB})

    delay_save.assert_not_called()


async def test_changes_write_the_delayed_snapshot(hass, hass_storage) -> None:
    store = TtlockBleFingerprintStore(hass)
    store.async_replace(MAC, {THUMB})
    store.async_set_name(MAC, THUMB, "Alice")
    await store._store.async_save(store._snapshot())

    assert hass_storage[STORAGE_KEY]["data"] == {MAC: {THUMB.token: "Alice"}}


async def test_locks_keep_separate_lists(hass) -> None:
    store = TtlockBleFingerprintStore(hass)
    store.async_replace(MAC, {THUMB})
    store.async_set_name(MAC, THUMB, "Alice")

    assert store.enrolled("11:22:33:44:55:66") is None
    assert store.name_of("11:22:33:44:55:66", THUMB) is None


async def test_every_entry_shares_one_store(hass) -> None:
    """Two instances over one storage key take turns dropping each other's writes."""
    from custom_components.ttlock_ble.fingerprint_store import (
        async_get_fingerprint_store,
    )

    first = await async_get_fingerprint_store(hass)
    first.async_replace(MAC, {THUMB})
    second = await async_get_fingerprint_store(hass)

    assert second is first
    assert second.enrolled(MAC) == [THUMB]
