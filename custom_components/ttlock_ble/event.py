"""
Event platform for ttlock_ble.

Surfaces historical operation records read from the lock's on-device
storage (fingerprint, keypad, IC card, etc.) every time the integration
connects or polls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.event import EventEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from ttlock_ble import LogOperate

from .connection import log_signal
from .entity import TtlockBleEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import LogEntry, VirtualKey

    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry


LOG_EVENT_TYPES: list[str] = [
    "unlock",
    "lock",
    "unlock_failed",
    "password_change",
    "other",
]


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create log-event entities per `VirtualKey`."""
    data = entry.runtime_data
    async_add_entities(
        TtlockBleLogEvent(data.coordinator, key) for key in data.virtual_keys
    )


def _classify_record(record_type: int) -> str:
    """Map a LogOperate record type to an HA event type."""
    unlock_types = {
        LogOperate.MOBILE_UNLOCK,
        LogOperate.KEYBOARD_PASSWORD_UNLOCK,
        LogOperate.IC_UNLOCK_SUCCEED,
        LogOperate.FR_UNLOCK_SUCCEED,
        LogOperate.BONG_UNLOCK,
        LogOperate.GATEWAY_UNLOCK,
        LogOperate.WIRELESS_KEY_FOB,
        LogOperate.WIRELESS_KEY_PAD,
        LogOperate.REMOTE_CONTROL_KEY,
    }
    lock_types = {
        LogOperate.OPERATE_BLE_LOCK,
        LogOperate.PASSCODE_LOCK,
        LogOperate.IC_LOCK,
        LogOperate.FR_LOCK,
    }
    fail_types = {
        LogOperate.ERROR_PASSWORD_UNLOCK,
        LogOperate.FR_UNLOCK_FAILED,
        LogOperate.APP_UNLOCK_FAILED_LOCK_REVERSE,
        LogOperate.PASSCODE_UNLOCK_FAILED_LOCK_REVERSE,
        LogOperate.IC_UNLOCK_FAILED_LOCK_REVERSE,
        LogOperate.FR_UNLOCK_FAILED_LOCK_REVERSE,
        LogOperate.PASSCODE_EXPIRED,
        LogOperate.PASSCODE_IN_BLACK_LIST,
    }
    password_types = {
        LogOperate.KEYBOARD_MODIFY_PASSWORD,
        LogOperate.KEYBOARD_REMOVE_SINGLE_PASSWORD,
        LogOperate.KEYBOARD_REMOVE_ALL_PASSWORDS,
        LogOperate.KEYBOARD_PASSWORD_KICKED,
        LogOperate.USE_DELETE_CODE,
        LogOperate.ADD_IC,
        LogOperate.CLEAR_IC_SUCCEED,
        LogOperate.DELETE_IC_SUCCEED,
        LogOperate.ADD_FR,
        LogOperate.DELETE_FR_SUCCEED,
    }
    if record_type in unlock_types:
        return "unlock"
    if record_type in lock_types:
        return "lock"
    if record_type in fail_types:
        return "unlock_failed"
    if record_type in password_types:
        return "password_change"
    return "other"


def _record_type_name(record_type: int) -> str:
    """Return a human-friendly name for the record type."""
    try:
        return LogOperate(record_type).name.lower()
    except ValueError:
        return str(record_type)


class TtlockBleLogEvent(TtlockBleEntity, EventEntity):
    """Fires when a new operation log entry is retrieved from the lock."""

    _attr_translation_key = "log"

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
    ) -> None:
        """Bind the entity to its key + coordinator."""
        super().__init__(coordinator, key)
        self._attr_event_types = LOG_EVENT_TYPES

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_log"

    async def async_added_to_hass(self) -> None:
        """Subscribe to the log dispatcher signal."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                log_signal(self._key.lockMac),
                self._on_log_entry,
            ),
        )

    @callback
    def _on_log_entry(self, entry: LogEntry) -> None:
        """Translate a LogEntry into an HA event fire."""
        event_type = _classify_record(entry.record_type)
        attributes: dict[str, object] = {
            "record_type": _record_type_name(entry.record_type),
            "battery": entry.lock_battery,
        }
        if entry.operate_date is not None:
            attributes["timestamp"] = entry.operate_date.isoformat()
        if entry.uid is not None:
            attributes["uid"] = entry.uid
        if entry.password is not None:
            attributes["credential"] = entry.password
        if entry.key_id is not None:
            attributes["key_id"] = entry.key_id
        if entry.accessory_battery is not None:
            attributes["accessory_battery"] = entry.accessory_battery
        self._trigger_event(event_type, attributes)
        self.async_write_ha_state()
