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

    from ttlock_ble import LogEntry

    from .data import TtlockBleConfigEntry, TtlockBleLogEventAttributes


LOG_EVENT_TYPES: list[str] = [
    "unlock",
    "lock",
    "unlock_failed",
    "password_change",
    "other",
]

# Record types whose `password` field is a working door code rather than an
# identifier. The SDK reuses one field for keypad codes, card numbers,
# fingerprint ids and fob MACs; only the first are secret, and an HA event
# attribute lands in the recorder database and is readable through the API
# by any user, so those never leave this module.
PASSCODE_RECORD_TYPES: frozenset[int] = frozenset(
    {
        LogOperate.KEYBOARD_PASSWORD_UNLOCK,
        LogOperate.KEYBOARD_MODIFY_PASSWORD,
        LogOperate.KEYBOARD_REMOVE_SINGLE_PASSWORD,
        LogOperate.ERROR_PASSWORD_UNLOCK,
        LogOperate.KEYBOARD_REMOVE_ALL_PASSWORDS,
        LogOperate.KEYBOARD_PASSWORD_KICKED,
        LogOperate.USE_DELETE_CODE,
        LogOperate.PASSCODE_EXPIRED,
        LogOperate.SPACE_INSUFFICIENT,
        LogOperate.PASSCODE_IN_BLACK_LIST,
        LogOperate.PASSCODE_LOCK,
        LogOperate.PASSCODE_UNLOCK_FAILED_LOCK_REVERSE,
        LogOperate.DOUBLE_CHECK_PASSCODE_UNLOCK,
        LogOperate.ADMIN_CODE_UNLOCK,
        LogOperate.ADD_PASSCODE_SUCCESSFULLY,
    },
)


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


UNLOCK_RECORD_TYPES: frozenset[int] = frozenset(
    {
        LogOperate.MOBILE_UNLOCK,
        LogOperate.SERVER_UNLOCK,
        LogOperate.KEYBOARD_PASSWORD_UNLOCK,
        LogOperate.IC_UNLOCK_SUCCEED,
        LogOperate.FR_UNLOCK_SUCCEED,
        LogOperate.BONG_UNLOCK,
        LogOperate.GATEWAY_UNLOCK,
        LogOperate.WIRELESS_KEY_FOB,
        LogOperate.WIRELESS_KEY_PAD,
        LogOperate.REMOTE_CONTROL_KEY,
        LogOperate.OPERATE_KEY_UNLOCK,
        LogOperate.DOOR_SENSOR_UNLOCK,
        LogOperate.QR_CODE_UNLOCK_SUCCESS,
        LogOperate.FACE_3D_UNLOCK_SUCCESS,
        LogOperate.APP_AUTH_KEY_UNLOCK_SUCCESS,
        LogOperate.GATEWAY_AUTH_KEY_UNLOCK_SUCCESS,
        LogOperate.DOUBLE_CHECK_KEY_UNLOCK,
        LogOperate.DOUBLE_CHECK_PASSCODE_UNLOCK,
        LogOperate.DOUBLE_CHECK_FINGER_PRINT_UNLOCK,
        LogOperate.DOUBLE_CHECK_CARD_UNLOCK,
        LogOperate.DOUBLE_CHECK_FACE_UNLOCK,
        LogOperate.DOUBLE_CHECK_KEY_FOB_UNLOCK,
        LogOperate.DOUBLE_CHECK_PALM_VEIN_UNLOCK,
        LogOperate.PALM_VEIN_UNLOCK_SUCCESS,
        LogOperate.ADMIN_CODE_UNLOCK,
        LogOperate.THIRD_DEVICE_UNLOCK_SUCCESS,
    },
)

LOCK_RECORD_TYPES: frozenset[int] = frozenset(
    {
        LogOperate.OPERATE_BLE_LOCK,
        LogOperate.PASSCODE_LOCK,
        LogOperate.IC_LOCK,
        LogOperate.FR_LOCK,
        LogOperate.DOOR_SENSOR_LOCK,
        LogOperate.OPERATE_KEY_LOCK,
        LogOperate.APP_DEAD_LOCK,
        LogOperate.FACE_3D_LOCK,
        LogOperate.PALM_VEIN_LOCK,
        LogOperate.THIRD_DEVICE_LOCK_SUCCESS,
    },
)

UNLOCK_FAILED_RECORD_TYPES: frozenset[int] = frozenset(
    {
        LogOperate.ERROR_PASSWORD_UNLOCK,
        LogOperate.FR_UNLOCK_FAILED,
        LogOperate.APP_UNLOCK_FAILED_LOCK_REVERSE,
        LogOperate.PASSCODE_UNLOCK_FAILED_LOCK_REVERSE,
        LogOperate.IC_UNLOCK_FAILED_LOCK_REVERSE,
        LogOperate.FR_UNLOCK_FAILED_LOCK_REVERSE,
        LogOperate.PASSCODE_EXPIRED,
        LogOperate.PASSCODE_IN_BLACK_LIST,
        LogOperate.IC_UNLOCK_FAILED,
        LogOperate.IC_UNLOCK_FAILED_BLACKLIST,
        LogOperate.QR_CODE_UNLOCK_FAILED,
        LogOperate.FACE_3D_UNLOCK_FAILED_LOCK_REVERSE,
        LogOperate.FACE_3D_UNLOCK_FAILED_INVALID_TIME,
        LogOperate.CPU_CARD_UNLOCK_FAILED,
        LogOperate.PALM_VEIN_UNLOCK_FAILED_LOCK_REVERSE,
        LogOperate.PALM_VEIN_UNLOCK_FAILED,
        LogOperate.CARD_UNLOCK_FAILED,
        LogOperate.THIRD_DEVICE_UNLOCK_FAILED_LOCK_REVERSE,
        LogOperate.THIRD_DEVICE_UNLOCK_FAILED_INVALID_TIME,
    },
)

# Credential management, whatever the credential is. The event type is
# named after passcodes because that is all the firmware could manage
# when it was added, and renaming it now would break every automation
# listening for it.
PASSWORD_CHANGE_RECORD_TYPES: frozenset[int] = frozenset(
    {
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
        LogOperate.CLEAR_FR_SUCCEED,
        LogOperate.FACE_3D_ADD_SUCCESS,
        LogOperate.FACE_3D_DELETE_SUCCESS,
        LogOperate.FACE_3D_CLEAR_SUCCESS,
        LogOperate.PALM_VEIN_ADD_SUCCESS,
        LogOperate.PALM_VEIN_DELETE_SUCCESS,
        LogOperate.PALM_VEIN_CLEAR_SUCCESS,
        LogOperate.ADD_PASSCODE_SUCCESSFULLY,
        LogOperate.ADD_THIRD_DEVICE,
        LogOperate.DELETE_THIRD_DEVICE,
        LogOperate.CLEAR_THIRD_DEVICE,
    },
)

# Records that are deliberately left as `other` because none of the four
# buckets is honest about them. Listed rather than left implicit so the
# coverage test can tell a considered omission from a forgotten record —
# `record_type` still names each one exactly, which is what an automation
# should match on.
UNBUCKETED_RECORD_TYPES: frozenset[int] = frozenset(
    {
        # Storage is full; nothing opened or closed.
        LogOperate.SPACE_INSUFFICIENT,
        # The lock restarted.
        LogOperate.DOOR_REBOOT,
        # Opened without a credential the lock recognises. Neither a
        # successful unlock nor a refused one, and guessing either way
        # would misreport a security event.
        LogOperate.ILLEGAL_UNLOCK,
        # The door was left open / someone went out; no bolt operation.
        LogOperate.DOOR_GO_OUT,
        # A verification step of a two-factor flow, not the unlock that
        # may or may not follow it.
        LogOperate.DOUBLE_CHECK_THIRD_DEVICE_VERIFY,
    },
)


def _classify_record(record_type: int) -> str:
    """Map a LogOperate record type to an HA event type."""
    if record_type in UNLOCK_RECORD_TYPES:
        return "unlock"
    if record_type in LOCK_RECORD_TYPES:
        return "lock"
    if record_type in UNLOCK_FAILED_RECORD_TYPES:
        return "unlock_failed"
    if record_type in PASSWORD_CHANGE_RECORD_TYPES:
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
    _attr_event_types = LOG_EVENT_TYPES

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
        attributes: TtlockBleLogEventAttributes = {
            "record_type": _record_type_name(entry.record_type),
            "battery": entry.lock_battery,
        }
        if entry.operate_date is not None:
            attributes["timestamp"] = entry.operate_date.isoformat()
        if entry.uid is not None:
            attributes["uid"] = entry.uid
        if entry.password is not None and entry.record_type not in (
            PASSCODE_RECORD_TYPES
        ):
            attributes["credential"] = entry.password
        if entry.key_id is not None:
            attributes["key_id"] = entry.key_id
        if entry.accessory_battery is not None:
            attributes["accessory_battery"] = entry.accessory_battery
        self._trigger_event(event_type, dict(attributes))
        self.async_write_ha_state()
