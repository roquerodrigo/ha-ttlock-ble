"""
Button platform for ttlock_ble — forcing an immediate fingerprint-list read.

Fingerprint changes have no dedicated push signal: neither the
advertisement's flags byte nor a live `LockEvent` push distinguishes a
fingerprint add/delete from any other log-worthy event (both only carry
the generic "there are unsynced records" signal the operation log already
rides). So unlike that log, there is nothing to wire a reactive read to -
this button is the deliberate alternative to a background polling timer,
which this integration's `update_interval=None` design treats battery
cost as a first-class reason to avoid.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory

from .entity import TtlockBleFingerprintsHubEntity
from .key_privileges import can_administer

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .data import TtlockBleConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one fingerprint-refresh button per lock this key may administer."""
    data = entry.runtime_data
    async_add_entities(
        TtlockBleRefreshFingerprintsButton(data.coordinator, key)
        for key in data.virtual_keys
        if can_administer(key)
    )


class TtlockBleRefreshFingerprintsButton(TtlockBleFingerprintsHubEntity, ButtonEntity):
    """
    Forces an immediate fingerprint-list read, bypassing the pacing interval.

    Lives on the "Fingerprints" hub device rather than the lock device -
    it is specifically about fingerprint state, not the lock as a whole.
    """

    _attr_translation_key = "refresh_fingerprints"
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_refresh_fingerprints"

    async def async_press(self) -> None:
        """Force the read. A session that did not land leaves state untouched."""
        await self.coordinator.async_refresh_fingerprints(self._key.lockMac)
