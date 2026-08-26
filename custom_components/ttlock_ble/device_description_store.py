"""Persisted per-lock hardware description for ttlock_ble."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.storage import Store

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import TtlockBleDeviceDescription

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.device_descriptions"
SAVE_DELAY_SECONDS = 10


class TtlockBleDeviceDescriptionStore:
    """
    Remember the hardware strings each lock has reported.

    Reading them costs a BLE session, and a lock only grants one while it
    is awake, so the answer is kept rather than asked for again on every
    start: a restarted Home Assistant shows the model and the firmware
    version of a lock nobody has touched in days, which is exactly when
    a user goes looking for them.

    Keyed by MAC rather than by entry, so a lock keeps its description
    across a reconfigure, and for the same reason a cloud entry and a
    manual entry describing the same lock agree.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Bind the descriptions to HA's storage helper."""
        self._store: Store[dict[str, TtlockBleDeviceDescription]] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
        )
        self._descriptions: dict[str, TtlockBleDeviceDescription] = {}

    async def async_load(self) -> None:
        """Read the persisted descriptions, tolerating a missing or empty file."""
        data = await self._store.async_load()
        if not data:
            return
        self._descriptions = dict(data)

    def get(self, mac: str) -> TtlockBleDeviceDescription | None:
        """Return what `mac` last reported about itself, if anything."""
        return self._descriptions.get(mac)

    def async_remember(self, mac: str, description: TtlockBleDeviceDescription) -> None:
        """Persist what `mac` reported, replacing any earlier answer."""
        self._descriptions[mac] = description
        self._store.async_delay_save(self._snapshot, SAVE_DELAY_SECONDS)

    def _snapshot(self) -> dict[str, TtlockBleDeviceDescription]:
        """Render the in-memory descriptions as the JSON the store writes."""
        return dict(self._descriptions)
