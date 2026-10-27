"""Binary sensor platform for ttlock_ble — BLE connection and door sensor state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import STATE_OFF, STATE_ON, EntityCategory
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity

from ttlock_ble import LogOperate

from .connection import connection_signal, log_signal
from .const import DOMAIN
from .entity import TtlockBleEntity

if TYPE_CHECKING:
    from homeassistant.core import CALLBACK_TYPE, HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import LogEntry, VirtualKey

    from .connection import TtlockBleConnection
    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry


DOOR_OPENED_RECORD_TYPES: frozenset[int] = frozenset(
    {
        LogOperate.DOOR_SENSOR_UNLOCK,
        LogOperate.DOOR_NOT_CLOSE_ALARM,
    },
)
DOOR_CLOSED_RECORD_TYPES: frozenset[int] = frozenset({LogOperate.DOOR_SENSOR_LOCK})


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the connection sensor per `VirtualKey`, and its door sensor once known."""
    data = entry.runtime_data
    async_add_entities(
        TtlockBleConnectionBinarySensor(data.coordinator, key)
        for key in data.virtual_keys
    )
    registry = er.async_get(hass)
    for key in data.virtual_keys:
        door = None
        if registry.async_get_entity_id(
            BINARY_SENSOR_DOMAIN,
            DOMAIN,
            _door_unique_id(key),
        ):
            door = TtlockBleDoorBinarySensor(data.coordinator, key)
            async_add_entities([door])
        entry.async_on_unload(
            _async_track_door_records(
                hass,
                data.coordinator,
                key,
                async_add_entities,
                door,
            ),
        )


def _door_unique_id(key: VirtualKey) -> str:
    """Return the unique id of the door sensor of the lock `key` opens."""
    return f"{key.lockMac}_door"


def _door_open_from_record(record_type: int) -> bool | None:
    """Return whether a record says the door is open, or `None` if it says nothing."""
    if record_type in DOOR_OPENED_RECORD_TYPES:
        return True
    if record_type in DOOR_CLOSED_RECORD_TYPES:
        return False
    return None


@callback
def _async_track_door_records(
    hass: HomeAssistant,
    coordinator: TtlockBleDataUpdateCoordinator,
    key: VirtualKey,
    async_add_entities: AddEntitiesCallback,
    door: TtlockBleDoorBinarySensor | None,
) -> CALLBACK_TYPE:
    """
    Feed door-sensor records to the lock's door entity, creating it on the first one.

    Only a lock with a paired sensor writes these records, so the entity
    is not offered to every lock that merely supports one. This listener
    stays the entity's only feed: records arrive in synchronous batches,
    and an entity that subscribed itself once added would miss the rest
    of the batch that created it.
    """
    tracked = door

    @callback
    def _on_log_entry(entry: LogEntry) -> None:
        nonlocal tracked
        is_open = _door_open_from_record(entry.record_type)
        if is_open is None:
            return
        if tracked is None:
            tracked = TtlockBleDoorBinarySensor(coordinator, key)
            async_add_entities([tracked])
        tracked.async_set_door_open(is_open=is_open)

    return async_dispatcher_connect(hass, log_signal(key.lockMac), _on_log_entry)


class TtlockBleConnectionBinarySensor(TtlockBleEntity, BinarySensorEntity):
    """Reports the live BLE link state for one lock."""

    _attr_translation_key = "connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_connection"

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


class TtlockBleDoorBinarySensor(TtlockBleEntity, BinarySensorEntity, RestoreEntity):
    """
    Reports whether the door is open, from the lock's door-sensor records.

    The sensor's state reaches Home Assistant only through the operation
    log, which is read when the lock advertises new records, so it lags
    the door by the few seconds that read takes.
    """

    _attr_translation_key = "door"
    _attr_device_class = BinarySensorDeviceClass.DOOR
    _is_open: bool | None = None
    _is_added: bool = False

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return _door_unique_id(self._key)

    @property
    def is_on(self) -> bool | None:
        """True while the door is open; `None` until a record or restore says."""
        return self._is_open

    @callback
    def async_set_door_open(self, *, is_open: bool) -> None:
        """Adopt what the latest door-sensor record says."""
        self._is_open = is_open
        if self._is_added:
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the last known door state unless a record already set one."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if (
            self._is_open is None
            and last_state is not None
            and last_state.state in (STATE_ON, STATE_OFF)
        ):
            self._is_open = last_state.state == STATE_ON
        self._is_added = True

    async def async_will_remove_from_hass(self) -> None:
        """Stop writing state once the entity is gone; the feed outlives it."""
        self._is_added = False
        await super().async_will_remove_from_hass()
