"""TtlockBleFingerprintEntity base class — one child device per enrolled fingerprint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import (
    ChildDeviceInfo,
    async_get_device_id_by_identifier,
)

from .entity import TtlockBleEntity
from .fingerprint_identifiers import fingerprint_identifier, fingerprints_hub_identifier

if TYPE_CHECKING:
    from ttlock_ble import VirtualKey

    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleEnrolledFingerprint


class TtlockBleFingerprintEntity(TtlockBleEntity):
    """Base entity living on the device of one enrolled fingerprint."""

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
        fingerprint: TtlockBleEnrolledFingerprint,
    ) -> None:
        """Bind to the coordinator, the lock's key and the fingerprint."""
        super().__init__(coordinator, key)
        self._fingerprint = fingerprint

    @property
    def device_info(self) -> ChildDeviceInfo:
        """
        A child of the fingerprints device, named by the fingerprint's number.

        A child device is nested under its parent on the devices page,
        where a `via_device` link would list every fingerprint as a
        top-level row. Its parent is referenced by registry id, which
        setup guarantees by registering the fingerprints device first.
        """
        parent_device_id = async_get_device_id_by_identifier(
            self.hass,
            fingerprints_hub_identifier(self._key.lockMac),
            config_entry_id=self.coordinator.config_entry.entry_id,
        )
        return ChildDeviceInfo(
            identifiers={fingerprint_identifier(self._key.lockMac, self._fingerprint)},
            parent_device_id=parent_device_id,
            name=str(self._fingerprint.number),
        )
