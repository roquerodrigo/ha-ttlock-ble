"""Binary sensor platform for ttlock_ble — live BLE connection state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .connection import connection_signal
from .entity import TtlockBleEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import VirtualKey

    from .connection import TtlockBleConnection
    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one connection binary sensor per `VirtualKey`."""
    data = entry.runtime_data
    async_add_entities(
        TtlockBleConnectionBinarySensor(data.coordinator, key)
        for key in data.virtual_keys
    )


class TtlockBleConnectionBinarySensor(TtlockBleEntity, BinarySensorEntity):
    """Reports the live BLE link state for one lock."""

    _attr_translation_key = "connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
    ) -> None:
        """Bind the binary sensor to its key + coordinator."""
        super().__init__(coordinator, key)
        self._attr_unique_id = f"{key.lockMac}_connection"

    @property
    def is_on(self) -> bool:
        """True iff the persistent BLE session to this lock is currently up."""
        return self._connection.is_connected

    @property
    def icon(self) -> str:
        """Bluetooth icon that mirrors the live link state."""
        return "mdi:bluetooth-connect" if self.is_on else "mdi:bluetooth-off"

    async def async_added_to_hass(self) -> None:
        """Subscribe to live BLE connect/disconnect transitions."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                connection_signal(self._key.lockMac),
                self._on_connection_state,
            ),
        )

    @callback
    def _on_connection_state(self, _connected: bool) -> None:  # noqa: FBT001
        """Push the freshest BLE link state into HA's state machine."""
        self.async_write_ha_state()

    @property
    def _connection(self) -> TtlockBleConnection:
        """Return the persistent BLE connection wrapper for this lock."""
        return self.coordinator.connections[self._key.lockMac]
