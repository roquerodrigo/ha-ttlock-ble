"""Binary sensor platform for ttlock_ble — Bluetooth presence."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
    async_address_present,
    async_register_callback,
    async_track_unavailable,
)
from homeassistant.const import EntityCategory
from homeassistant.core import callback

from .entity import TtlockBleEntity

if TYPE_CHECKING:
    from homeassistant.components.bluetooth import (
        BluetoothChange,
        BluetoothServiceInfoBleak,
    )
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import VirtualKey

    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one presence binary sensor per `VirtualKey`."""
    data = entry.runtime_data
    async_add_entities(
        TtlockBlePresenceBinarySensor(data.coordinator, key)
        for key in data.virtual_keys
    )


class TtlockBlePresenceBinarySensor(TtlockBleEntity, BinarySensorEntity):
    """Reports if the lock is currently advertising in BLE range."""

    _attr_translation_key = "presence"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
    ) -> None:
        """Bind the binary sensor to its key + coordinator."""
        super().__init__(coordinator, key)
        self._attr_unique_id = f"{key.lockMac}_presence"

    @property
    def is_on(self) -> bool:
        """True iff the lock has advertised in HA's recent-tracking window."""
        return async_address_present(
            self.hass,
            self._key.lockMac,
            connectable=True,
        )

    @property
    def icon(self) -> str:
        """Bluetooth icon that mirrors the live presence state."""
        return "mdi:bluetooth" if self.is_on else "mdi:bluetooth-off"

    async def async_added_to_hass(self) -> None:
        """Subscribe to advertisement + unavailable callbacks for live updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_register_callback(
                self.hass,
                self._on_advertisement,
                BluetoothCallbackMatcher(
                    address=self._key.lockMac,
                    connectable=True,
                ),
                BluetoothScanningMode.PASSIVE,
            ),
        )
        self.async_on_remove(
            async_track_unavailable(
                self.hass,
                self._on_unavailable,
                self._key.lockMac,
                connectable=True,
            ),
        )

    @callback
    def _on_advertisement(
        self,
        _service_info: BluetoothServiceInfoBleak,
        _change: BluetoothChange,
    ) -> None:
        """Lock is broadcasting — refresh state."""
        self.async_write_ha_state()

    @callback
    def _on_unavailable(self, _service_info: BluetoothServiceInfoBleak) -> None:
        """Lock has stopped broadcasting — refresh state."""
        self.async_write_ha_state()
