"""TtlockBleFingerprintsHubEntity base class — the device holding the fingerprints."""

from __future__ import annotations

from homeassistant.helpers.device_registry import (
    DeviceInfo,
    async_get_device_id_by_identifier,
)

from .const import MANUFACTURER
from .entity import TtlockBleEntity
from .fingerprint_identifiers import fingerprints_hub_identifier, lock_identifier


class TtlockBleFingerprintsHubEntity(TtlockBleEntity):
    """Base entity living on the 'Fingerprints' device under a lock."""

    @property
    def device_info(self) -> DeviceInfo:
        """One fingerprints device per lock, reached through the lock's own."""
        return DeviceInfo(
            identifiers={fingerprints_hub_identifier(self._key.lockMac)},
            via_device_id=async_get_device_id_by_identifier(
                self.hass,
                lock_identifier(self._key.lockMac),
                config_entry_id=self.coordinator.config_entry.entry_id,
            ),
            translation_key="fingerprints",
            translation_placeholders={"lock": self._lock_name},
            manufacturer=MANUFACTURER,
        )
