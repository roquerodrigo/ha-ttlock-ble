"""Binary sensor platform for ttlock_ble — BLE connection, door and passage mode."""

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
from homeassistant.util import dt as dt_util

from ttlock_ble import LogOperate

from .connection import connection_signal, log_signal
from .const import DOMAIN
from .entity import TtlockBleEntity
from .key_privileges import can_manage_passage_mode
from .passage_mode import describe_slot, slot_covers, slot_from_description
from .passage_mode_entity import TtlockBlePassageModeEntity

if TYPE_CHECKING:
    from homeassistant.core import CALLBACK_TYPE, HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import LogEntry, VirtualKey

    from .connection import TtlockBleConnection
    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry, TtlockBlePassageModeAttributes


DOOR_OPENED_RECORD_TYPES: frozenset[int] = frozenset(
    {
        LogOperate.DOOR_SENSOR_UNLOCK,
        LogOperate.DOOR_NOT_CLOSE_ALARM,
    },
)
DOOR_CLOSED_RECORD_TYPES: frozenset[int] = frozenset({LogOperate.DOOR_SENSOR_LOCK})

# What rebuilding a slot raises on a restored attribute that is not one.
MALFORMED_SLOT_ERRORS = (KeyError, TypeError, ValueError)


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
    async_add_entities(
        TtlockBlePassageModeBinarySensor(data.coordinator, key)
        for key in data.virtual_keys
        if can_manage_passage_mode(key)
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


class TtlockBlePassageModeBinarySensor(
    TtlockBlePassageModeEntity, BinarySensorEntity, RestoreEntity
):
    """
    Whether a passage mode slot is in effect on the lock right now.

    While one is, the lock no longer relocks on its own after an unlock.
    It is worked out from the slots the lock last listed (see
    `TtlockBlePassageModeEntity`), so it is unknown until a session has
    carried a read, and only created for a key that can ask: the firmware
    lists the slots to an admin key alone.

    On says a slot covers this minute, not that the bolt is drawn back:
    the lock still has to be unlocked once inside the slot to stay so.

    It is a `RestoreEntity` for the slots rather than for the state: the
    list it last showed is handed back to the coordinator after a restart,
    so the sensor follows the clock again at once instead of waiting for
    the next session, which then replaces the list.
    """

    _attr_translation_key = "passage_mode"
    _attr_icon = "mdi:door-open"

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_passage_mode"

    @property
    def is_on(self) -> bool | None:
        """Return whether a known slot covers the current minute."""
        slots = self._slots
        if slots is None:
            return None
        now = dt_util.now()
        return any(slot_covers(slot, now) for slot in slots)

    @property
    def extra_state_attributes(self) -> TtlockBlePassageModeAttributes:
        """Return the slots the lock was last known to hold."""
        return {"slots": [describe_slot(slot) for slot in self._slots or []]}

    async def async_added_to_hass(self) -> None:
        """Restore the slots this entity last showed, then follow the clock."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._restore_slots(last_state.attributes.get("slots"))
            self._async_arm_transition()

    def _restore_slots(self, described: object) -> None:
        """Hand the slots of a restored state back to the coordinator, if it has any."""
        if not isinstance(described, list):
            return
        try:
            slots = [slot_from_description(description) for description in described]
        except MALFORMED_SLOT_ERRORS:
            return
        self.coordinator.async_restore_passage_slots(self._key.lockMac, slots)


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
