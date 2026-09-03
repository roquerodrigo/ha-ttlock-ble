"""Binary sensor platform for ttlock_ble — live BLE connection and passage mode state."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .connection import connection_signal, passage_mode_signal
from .entity import TtlockBleEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .connection import TtlockBleConnection
    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry

DAY_NAMES = {
    0: "everyday",
    1: "monday",
    2: "tuesday",
    3: "wednesday",
    4: "thursday",
    5: "friday",
    6: "saturday",
    7: "sunday",
}


def is_passage_mode_active(
    schedules: list[dict[str, Any]],
    now: datetime,
) -> bool:
    """Return True if current wall-clock time is inside any passage mode schedule."""
    if not schedules:
        return False

    current_time_minutes = now.hour * 60 + now.minute
    iso_weekday = now.isoweekday()  # 1 = Monday, 7 = Sunday
    current_day = now.day
    current_month = now.month

    for slot in schedules:
        st_type = slot.get("type", 1)
        start_min = slot.get("start_hour", 0) * 60 + slot.get("start_minute", 0)
        end_min = slot.get("end_hour", 0) * 60 + slot.get("end_minute", 0)

        # Check if day matches
        day_match = False
        if st_type == 1:
            w_day = slot.get("week_or_day")
            day_match = w_day == 0 or w_day == "everyday" or w_day == iso_weekday
        elif st_type == 2:
            day_match = (
                slot.get("month") == current_month
                and slot.get("week_or_day") == current_day
            )

        if not day_match:
            continue

        # Check time window
        if start_min <= current_time_minutes < end_min:
            return True

    return False


def get_next_passage_mode_transition(
    schedules: list[dict[str, Any]],
    now: datetime,
) -> datetime | None:
    """Calculate the exact next transition timestamp (start or end of a slot)."""
    if not schedules:
        return None

    transitions: list[datetime] = []
    # Search over the next 8 days to find the earliest transition
    for day_offset in range(8):
        target_date = (now + timedelta(days=day_offset)).date()
        target_weekday = target_date.isoweekday()

        for slot in schedules:
            st_type = slot.get("type", 1)
            day_match = False
            if st_type == 1:
                w_day = slot.get("week_or_day")
                day_match = (
                    w_day == 0 or w_day == "everyday" or w_day == target_weekday
                )
            elif st_type == 2:
                day_match = (
                    slot.get("month") == target_date.month
                    and slot.get("week_or_day") == target_date.day
                )

            if not day_match:
                continue

            # Start transition
            dt_start = datetime.combine(
                target_date,
                time(slot.get("start_hour", 0), slot.get("start_minute", 0)),
                tzinfo=now.tzinfo,
            )
            if dt_start > now:
                transitions.append(dt_start)

            # End transition
            dt_end = datetime.combine(
                target_date,
                time(slot.get("end_hour", 0), slot.get("end_minute", 0)),
                tzinfo=now.tzinfo,
            )
            if dt_end > now:
                transitions.append(dt_end)

    if not transitions:
        return None

    return min(transitions)


def format_schedules_attribute(
    schedules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Format schedule slots for human-readable state attributes."""
    formatted = []
    for s in schedules:
        week_or_day = s.get("week_or_day", 1)
        formatted.append({
            "type": "weekly" if s.get("type") == 1 else "monthly",
            "day": (
                DAY_NAMES.get(week_or_day, str(week_or_day))
                if s.get("type") == 1
                else week_or_day
            ),
            "start_time": f"{s.get('start_hour', 0):02d}:{s.get('start_minute', 0):02d}",
            "end_time": f"{s.get('end_hour', 0):02d}:{s.get('end_minute', 0):02d}",
        })
    return formatted


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create binary sensors for each VirtualKey."""
    data = entry.runtime_data
    entities: list[BinarySensorEntity] = []

    for key in data.virtual_keys:
        conn = data.connections[key.lockMac]
        entities.append(TtlockBleConnectionBinarySensor(data.coordinator, key))
        entities.append(
            TtlockBlePassageModeActiveBinarySensor(data.coordinator, key, conn)
        )

    async_add_entities(entities)


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


class TtlockBlePassageModeActiveBinarySensor(
    TtlockBleEntity,
    RestoreEntity,
    BinarySensorEntity,
):
    """Reports whether passage mode is currently holding the door unlocked."""

    _attr_translation_key = "passage_mode_active"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
        connection: TtlockBleConnection,
    ) -> None:
        """Bind entity to coordinator, key, and connection."""
        super().__init__(coordinator, key)
        self._connection = connection
        self._schedules: list[dict[str, Any]] = list(connection.passage_schedules)
        self._unsub_transition: callback | None = None

    @property
    def unique_id(self) -> str:
        """Return a stable unique id."""
        return f"{self._key.lockMac}_passage_mode_active"

    @property
    def is_on(self) -> bool:
        """True iff current time falls inside a configured passage window."""
        return is_passage_mode_active(self._schedules, dt_util.now())

    @property
    def icon(self) -> str:
        """Door open icon when passage mode is actively unlocked."""
        return "mdi:door-open" if self.is_on else "mdi:door-closed-lock"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return schedule metadata attributes."""
        return {
            "schedules": format_schedules_attribute(self._schedules),
            "raw_schedules": self._schedules,
            "schedule_count": len(self._schedules),
            "has_schedule": bool(self._schedules),
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to schedule updates and restore prior state."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            raw = last_state.attributes.get("raw_schedules")
            if raw and not self._schedules:
                self._schedules = list(raw)

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                passage_mode_signal(self._key.lockMac),
                self._on_passage_mode_update,
            ),
        )
        self._schedule_next_transition()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel any active transition timer."""
        if self._unsub_transition is not None:
            self._unsub_transition()
            self._unsub_transition = None
        await super().async_will_remove_from_hass()

    @callback
    def _on_passage_mode_update(self, schedules_or_active: Any) -> None:
        """Update schedules from dispatcher signal."""
        if isinstance(schedules_or_active, list):
            self._schedules = list(schedules_or_active)
        elif self._connection.passage_schedules:
            self._schedules = list(self._connection.passage_schedules)
        self.async_write_ha_state()
        self._schedule_next_transition()

    @callback
    def _schedule_next_transition(self) -> None:
        """Schedule a local timer for the exact start/end boundary."""
        if self._unsub_transition is not None:
            self._unsub_transition()
            self._unsub_transition = None

        next_trans = get_next_passage_mode_transition(self._schedules, dt_util.now())
        if next_trans is not None:
            self._unsub_transition = async_track_point_in_time(
                self.hass,
                self._on_transition_point,
                next_trans,
            )

    @callback
    def _on_transition_point(self, _now: datetime) -> None:
        """Handle exact transition boundary."""
        self._unsub_transition = None
        self.async_write_ha_state()
        self._schedule_next_transition()
