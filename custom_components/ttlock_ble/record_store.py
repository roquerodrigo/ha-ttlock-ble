"""Persisted operation-log cursor for ttlock_ble."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from homeassistant.helpers.storage import Store

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.records"
SAVE_DELAY_SECONDS = 10

# Record ids kept per lock. The firmware hands back everything unsynced
# since its last cursor sync, so only the recent end of the log is ever
# compared against; the cap keeps the file from growing for the lifetime
# of the lock.
MAX_RECORDS_PER_LOCK = 250


class TtlockBleStoredCursor(TypedDict):
    """One lock's place in its operation log, as written to storage."""

    seeded: bool
    records: list[int]


class TtlockBleRecordStore:
    """
    Remember which operation records each lock has already reported.

    Without this the set lives only in memory, so every Home Assistant
    restart forgot where the log had been read up to. The lock answers a
    fetch with everything unsynced since its own cursor sync, which can
    be days of history, so the integration had to discard the whole
    first fetch after each start to avoid replaying it — and that
    discarded genuinely new records too, whenever something happened at
    the door shortly after a restart.

    `seeded` is stored separately from the ids because the two are not
    the same fact. A lock whose log was already synced seeds an empty
    set, and an empty set is indistinguishable from never having looked;
    without the flag that lock would seed again after every restart and
    keep swallowing its first real record.

    Keyed by MAC rather than by entry so a lock keeps its cursor across
    a reconfigure, and the ids are stored rather than a high-water mark
    because the firmware's numbering is not guaranteed to be monotonic.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Bind the cursor to HA's storage helper."""
        self._store: Store[dict[str, TtlockBleStoredCursor]] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
        )
        self._cursors: dict[str, TtlockBleStoredCursor] = {}

    async def async_load(self) -> None:
        """Read the persisted cursors, tolerating a missing or empty file."""
        data = await self._store.async_load()
        if not data:
            return
        self._cursors = dict(data)

    def seen(self, mac: str) -> set[int]:
        """Return the record ids already reported for `mac`."""
        cursor = self._cursors.get(mac)
        return set(cursor["records"]) if cursor else set()

    def is_seeded(self, mac: str) -> bool:
        """Report whether `mac` has already had its backlog pass."""
        cursor = self._cursors.get(mac)
        return bool(cursor and cursor["seeded"])

    def async_remember(self, mac: str, seen: set[int]) -> None:
        """Persist `seen` for `mac`, keeping only the most recent ids."""
        self._cursors[mac] = {
            "seeded": True,
            "records": sorted(seen)[-MAX_RECORDS_PER_LOCK:],
        }
        self._store.async_delay_save(self._snapshot, SAVE_DELAY_SECONDS)

    def _snapshot(self) -> dict[str, TtlockBleStoredCursor]:
        """Render the in-memory cursors as the JSON the store writes."""
        return dict(self._cursors)
