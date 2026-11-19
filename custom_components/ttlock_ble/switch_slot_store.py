"""Persisted per-lock record of the passage mode slots the switch wrote."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.singleton import singleton
from homeassistant.helpers.storage import Store
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN
from .passage_mode import slot_from_record, slot_to_record

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ttlock_ble import PassageModeSlot

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.switch_slots"


class TtlockBleSwitchSlotStore:
    """
    Remember which passage mode slots the switch put on each lock.

    A lock holds every slot alike, whoever wrote it: a schedule from the
    official app, one from `set_passage_mode` and the ones the switch left
    on all look the same. Turning the switch off has to remove its own and
    nothing else, so it is recorded here, and it is recorded before it is
    written - a record lost in a crash seconds after the write is exactly
    the case this exists for, so it is saved at once.

    Keyed by MAC rather than by entry, like the other stores, so a
    reconfigure does not orphan it.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Bind the records to HA's storage helper."""
        self._store: Store[dict[str, list[list[int]]]] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
        )
        self._slots: dict[str, list[list[int]]] = {}

    async def async_load(self) -> None:
        """Read the persisted records, tolerating a missing or empty file."""
        data = await self._store.async_load()
        if not data:
            return
        self._slots = dict(data)

    def get(self, mac: str) -> list[PassageModeSlot]:
        """Return the slots the switch wrote to `mac` and has not yet removed."""
        return [slot_from_record(record) for record in self._slots.get(mac, [])]

    async def async_remember(self, mac: str, slots: list[PassageModeSlot]) -> None:
        """Persist the slots the switch owns on `mac`, replacing the earlier record."""
        if not slots:
            await self.async_forget(mac)
            return
        self._slots[mac] = [slot_to_record(slot) for slot in slots]
        await self._store.async_save(dict(self._slots))

    async def async_forget(self, mac: str) -> None:
        """Drop the record of `mac` once the switch owns nothing there."""
        if self._slots.pop(mac, None) is not None:
            await self._store.async_save(dict(self._slots))


STORE_KEY: HassKey[TtlockBleSwitchSlotStore] = HassKey(f"{DOMAIN}_switch_slot_store")


@singleton(STORE_KEY, async_=True)
async def async_get_switch_slot_store(hass: HomeAssistant) -> TtlockBleSwitchSlotStore:
    """
    Return the one store this Home Assistant instance shares.

    One instance per entry writes the whole file from what it loaded, so
    two entries would take turns dropping each other's newer records.
    """
    store = TtlockBleSwitchSlotStore(hass)
    await store.async_load()
    return store
