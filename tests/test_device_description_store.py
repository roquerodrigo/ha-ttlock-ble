"""Coverage for the persisted per-lock hardware description."""

from __future__ import annotations

from custom_components.ttlock_ble.device_description_store import (
    STORAGE_KEY,
    STORAGE_VERSION,
    TtlockBleDeviceDescriptionStore,
)

MAC = "AA:BB:CC:DD:EE:FF"
DESCRIPTION = {
    "model": "SN534-4P-T78-BELL",
    "hardware_version": "1.7",
    "firmware_version": "6.5.20.24121101",
}


async def test_load_tolerates_a_missing_file(hass) -> None:
    store = TtlockBleDeviceDescriptionStore(hass)
    await store.async_load()
    assert store.get(MAC) is None


async def test_load_restores_the_persisted_description(hass, hass_storage) -> None:
    hass_storage[STORAGE_KEY] = {
        "version": STORAGE_VERSION,
        "data": {MAC: DESCRIPTION},
    }
    store = TtlockBleDeviceDescriptionStore(hass)
    await store.async_load()
    assert store.get(MAC) == DESCRIPTION


async def test_remember_replaces_the_earlier_answer(hass) -> None:
    """A firmware upgrade changes what the lock reports; the newer answer wins."""
    store = TtlockBleDeviceDescriptionStore(hass)
    store.async_remember(MAC, DESCRIPTION)
    upgraded = {**DESCRIPTION, "firmware_version": "6.5.21.25010101"}
    store.async_remember(MAC, upgraded)
    assert store.get(MAC) == upgraded


async def test_remember_writes_the_delayed_snapshot(hass, hass_storage) -> None:
    store = TtlockBleDeviceDescriptionStore(hass)
    store.async_remember(MAC, DESCRIPTION)
    await store._store.async_save(store._snapshot())
    assert hass_storage[STORAGE_KEY]["data"] == {MAC: DESCRIPTION}


async def test_locks_keep_separate_descriptions(hass) -> None:
    other = "11:22:33:44:55:66"
    store = TtlockBleDeviceDescriptionStore(hass)
    store.async_remember(MAC, DESCRIPTION)
    assert store.get(other) is None
