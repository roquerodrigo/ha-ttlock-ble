"""TtlockBleEntity base class — one device per `VirtualKey`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import (
    CONNECTION_BLUETOOTH,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, MANUFACTURER
from .coordinator import TtlockBleDataUpdateCoordinator

if TYPE_CHECKING:
    from ttlock_ble import VirtualKey

    from .data import TtlockBleLockState


class TtlockBleEntity(CoordinatorEntity[TtlockBleDataUpdateCoordinator]):
    """Base entity tied to a specific lock (`VirtualKey`)."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
    ) -> None:
        """Bind to the coordinator and the per-lock virtual key."""
        super().__init__(coordinator)
        self._key = key

    @property
    def device_info(self) -> DeviceInfo:
        """
        One Home Assistant device per physical lock, keyed by MAC.

        Model, hardware and firmware come from what the lock itself
        reported the last time one was read off it. Until then the model
        falls back to the protocol version carried by the key, which is
        the only thing known about a lock nobody has connected to yet.
        """
        mac = format_mac(self._key.lockMac)
        description = self.coordinator.async_device_description(self._key.lockMac)
        model = None if description is None else description["model"]
        return DeviceInfo(
            identifiers={(DOMAIN, mac)},
            connections={(CONNECTION_BLUETOOTH, mac)},
            name=self._key.lockAlias or self._key.lockName or self._key.lockMac,
            manufacturer=MANUFACTURER,
            model=model or self._protocol_model,
            hw_version=None if description is None else description["hardware_version"],
            sw_version=None if description is None else description["firmware_version"],
        )

    @property
    def _protocol_model(self) -> str:
        """Return the protocol version the key carries, as a model string."""
        return (
            f"Protocol {self._key.lockVersion.protocolType}."
            f"{self._key.lockVersion.protocolVersion}"
        )

    @property
    def _lock_state(self) -> TtlockBleLockState | None:
        """Return the per-lock state snapshot from the coordinator, if any."""
        if self.coordinator.data is None:
            return None  # type: ignore[unreachable]
        return self.coordinator.data.get(self._key.lockMac)
