"""Persisted fingerprint list and the names given to each fingerprint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.singleton import singleton
from homeassistant.helpers.storage import Store
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN
from .data import TtlockBleEnrolledFingerprint

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.fingerprints"
SAVE_DELAY_SECONDS = 10


class TtlockBleFingerprintStore:
    """
    The fingerprints each lock last listed, and whose each one is.

    The lock knows a fingerprint only by its number, so the person it
    belongs to is something only the user can say, and it has to outlive
    a restart. Keeping the list next to the names is what lets the
    fingerprint entities come back at setup without a session, and lets
    a fingerprint the lock dropped take its name with it.

    Keyed by MAC rather than by entry, so a lock keeps its names across a
    reconfigure. An empty name stands for a fingerprint nobody named yet.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Bind the store to HA's storage helper."""
        self._store: Store[dict[str, dict[str, str]]] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
        )
        self._names: dict[str, dict[str, str]] = {}

    async def async_load(self) -> None:
        """Read the persisted lists, tolerating a missing or empty file."""
        data = await self._store.async_load()
        if not data:
            return
        self._names = {mac: dict(names) for mac, names in data.items()}

    def enrolled(self, mac: str) -> list[TtlockBleEnrolledFingerprint] | None:
        """Return the fingerprints `mac` last listed, or `None` before any read."""
        names = self._names.get(mac)
        if names is None:
            return None
        fingerprints = (
            TtlockBleEnrolledFingerprint.from_token(token) for token in names
        )
        return sorted(
            (fingerprint for fingerprint in fingerprints if fingerprint is not None),
            key=lambda fingerprint: fingerprint.number,
        )

    def name_of(
        self, mac: str, fingerprint: TtlockBleEnrolledFingerprint
    ) -> str | None:
        """Return the name given to `fingerprint`, or `None` when it has none."""
        return self._names.get(mac, {}).get(fingerprint.token) or None

    def async_set_name(
        self, mac: str, fingerprint: TtlockBleEnrolledFingerprint, name: str
    ) -> None:
        """Name `fingerprint`; an empty name clears the one it had."""
        self._names.setdefault(mac, {})[fingerprint.token] = name.strip()
        self._store.async_delay_save(self._snapshot, SAVE_DELAY_SECONDS)

    def async_replace(
        self, mac: str, fingerprints: set[TtlockBleEnrolledFingerprint]
    ) -> None:
        """Adopt the list `mac` just read, keeping the names still enrolled."""
        previous = self._names.get(mac)
        current = {
            fingerprint.token: (previous or {}).get(fingerprint.token, "")
            for fingerprint in fingerprints
        }
        if current == previous:
            return
        self._names[mac] = current
        self._store.async_delay_save(self._snapshot, SAVE_DELAY_SECONDS)

    def _snapshot(self) -> dict[str, dict[str, str]]:
        """Render the in-memory lists as the JSON the store writes."""
        return {mac: dict(names) for mac, names in self._names.items()}


STORE_KEY: HassKey[TtlockBleFingerprintStore] = HassKey(f"{DOMAIN}_fingerprint_store")


@singleton(STORE_KEY, async_=True)
async def async_get_fingerprint_store(hass: HomeAssistant) -> TtlockBleFingerprintStore:
    """
    Return the one store this Home Assistant instance shares.

    The file is keyed by MAC and holds every lock of every entry, so one
    instance per entry would let the last one to write drop the names
    another entry had saved in the meantime.
    """
    store = TtlockBleFingerprintStore(hass)
    await store.async_load()
    return store
