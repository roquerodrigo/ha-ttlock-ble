"""Persisted per-lock record of when its clock was last checked."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.singleton import singleton
from homeassistant.helpers.storage import Store
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import TtlockBleClockSync

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.clock_syncs"
SAVE_DELAY_SECONDS = 10


class TtlockBleClockSyncStore:
    """
    Remember when each lock's clock was last compared against local time.

    The comparison rides on a session another read already opened, but
    the decision to run it is paced in days. Holding that timestamp only
    in memory would restart the pacing on every Home Assistant restart,
    and a lock that is reachable often would then be read on every one
    of them for an answer that moves by seconds a week.

    Keyed by MAC rather than by entry, for the same reason the device
    descriptions are: a lock keeps its history across a reconfigure, and
    a cloud entry and a manual entry describing the same lock agree.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Bind the records to HA's storage helper."""
        self._store: Store[dict[str, TtlockBleClockSync]] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
        )
        self._syncs: dict[str, TtlockBleClockSync] = {}

    async def async_load(self) -> None:
        """Read the persisted records, tolerating a missing or empty file."""
        data = await self._store.async_load()
        if not data:
            return
        self._syncs = dict(data)

    def get(self, mac: str) -> TtlockBleClockSync | None:
        """Return the last clock comparison for `mac`, if there was one."""
        return self._syncs.get(mac)

    def async_remember(self, mac: str, sync: TtlockBleClockSync) -> None:
        """Persist a comparison for `mac`, replacing any earlier one."""
        self._syncs[mac] = sync
        self._store.async_delay_save(self._snapshot, SAVE_DELAY_SECONDS)

    def _snapshot(self) -> dict[str, TtlockBleClockSync]:
        """Render the in-memory records as the JSON the store writes."""
        return dict(self._syncs)


STORE_KEY: HassKey[TtlockBleClockSyncStore] = HassKey(f"{DOMAIN}_clock_sync_store")


@singleton(STORE_KEY, async_=True)
async def async_get_clock_sync_store(hass: HomeAssistant) -> TtlockBleClockSyncStore:
    """
    Return the one store this Home Assistant instance shares.

    One instance per entry writes the whole file from what it loaded, so
    two entries would take turns dropping each other's newer records.
    """
    store = TtlockBleClockSyncStore(hass)
    await store.async_load()
    return store
