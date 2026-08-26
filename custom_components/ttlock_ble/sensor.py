"""Sensor platform for ttlock_ble — battery level and last contact."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.components.bluetooth import (
    MONOTONIC_TIME,
    async_last_service_info,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import dt as dt_util

from .connection import event_signal
from .entity import TtlockBleEntity

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import LockEvent, VirtualKey

    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the battery and last-seen sensors for every `VirtualKey`."""
    data = entry.runtime_data
    async_add_entities(
        sensor
        for key in data.virtual_keys
        for sensor in (
            TtlockBleBatterySensor(data.coordinator, key),
            TtlockBleLastSeenSensor(data.coordinator, key),
        )
    )


class TtlockBleBatterySensor(TtlockBleEntity, SensorEntity):
    """Battery level reported by the lock — refreshed on poll and on every push."""

    _attr_translation_key = "battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
    ) -> None:
        """Bind the sensor to its key + coordinator."""
        super().__init__(coordinator, key)
        self._attr_native_value: int | None = None
        self._sync_from_coordinator()

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_battery"

    async def async_added_to_hass(self) -> None:
        """Subscribe to push-event notifications for the lock's MAC."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                event_signal(self._key.lockMac),
                self._on_lock_event,
            ),
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Adopt the coordinator's freshest battery reading, if any."""
        self._sync_from_coordinator()
        super()._handle_coordinator_update()

    @callback
    def _on_lock_event(self, event: LockEvent) -> None:
        """Adopt the battery byte the lock embedded in its push payload."""
        if event.battery is None:
            return
        self._attr_native_value = event.battery
        self.async_write_ha_state()

    def _sync_from_coordinator(self) -> None:
        """Copy `battery_level` from the coordinator snapshot, if known."""
        state = self._lock_state
        if state is None:
            return
        battery = state.get("battery_level")
        if battery is None:
            return
        self._attr_native_value = battery


class TtlockBleLastSeenSensor(TtlockBleEntity, SensorEntity):
    """
    When Home Assistant last received an advertisement from the lock.

    A lock that is working normally is silent most of the time: it holds
    no connection, and its own advertisements are the only sign it is
    still there. This reports the freshness of that sign, which is what
    separates "idle" from "out of range" — a distinction the connection
    sensor cannot make, because the session is down in both cases.

    The value is read from the bluetooth manager's own history rather
    than from the advertisement callback, because that callback is not
    told about an advertisement whose payload matches the previous one.
    An idle lock repeats the same bytes for as long as nothing about it
    changes, so a sensor driven by the callback stops moving while the
    lock is in perfect health — which is precisely backwards.
    """

    _attr_translation_key = "last_seen"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:bluetooth-audio"

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
    ) -> None:
        """Bind the sensor to its key + coordinator."""
        super().__init__(coordinator, key)
        self._reported_at: float | None = None
        self._attr_native_value: datetime | None = None

    @property
    def should_poll(self) -> bool:
        """
        Poll, unlike the other entities here.

        Nothing notifies us when the bluetooth manager records an
        advertisement it decided not to dispatch, and those are exactly
        the ones this sensor exists to count.
        """
        return True

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_last_seen"

    @property
    def native_value(self) -> datetime | None:
        """
        Return when the last advertisement arrived, as a wall-clock time.

        The stored reception time is monotonic, so it is converted on
        read and then cached against it: recomputing on every poll would
        walk the timestamp by a fraction of a second each time and write
        a new state for an advertisement that never changed.
        """
        service_info = async_last_service_info(
            self.hass,
            self._key.lockMac,
            connectable=False,
        )
        if service_info is None:
            return self._attr_native_value
        if service_info.time != self._reported_at:
            self._reported_at = service_info.time
            age = MONOTONIC_TIME() - service_info.time
            self._attr_native_value = dt_util.utcnow() - timedelta(seconds=age)
        return self._attr_native_value
