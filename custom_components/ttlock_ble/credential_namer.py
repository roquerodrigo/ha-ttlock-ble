"""TtlockBleCredentialNamer — who an operation-log record's credential belongs to."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import (
    async_get as async_get_device_registry,
)

from ttlock_ble import LogOperate

from .data import TtlockBleEnrolledFingerprint
from .fingerprint_identifiers import fingerprint_identifier

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ttlock_ble import LogEntry

HOME_ASSISTANT_NAME = "Home Assistant"

FINGERPRINT_RECORD_TYPES: frozenset[int] = frozenset(
    {
        LogOperate.FR_UNLOCK_SUCCEED,
        LogOperate.ADD_FR,
        LogOperate.FR_UNLOCK_FAILED,
        LogOperate.DELETE_FR_SUCCEED,
        LogOperate.FR_LOCK,
        LogOperate.FR_UNLOCK_FAILED_LOCK_REVERSE,
        LogOperate.DOUBLE_CHECK_FINGER_PRINT_UNLOCK,
    },
)

# Commands sent over BLE by an app holding an eKey. This integration sends
# them with a zeroed user id, while the official app sends its account's.
BLE_APP_RECORD_TYPES: frozenset[int] = frozenset(
    {
        LogOperate.MOBILE_UNLOCK,
        LogOperate.OPERATE_BLE_LOCK,
        LogOperate.APP_UNLOCK_FAILED_LOCK_REVERSE,
        LogOperate.APP_DEAD_LOCK,
    },
)


class TtlockBleCredentialNamer:
    """Names the credential behind a record, for the locks of one entry."""

    def __init__(self, hass: HomeAssistant, config_entry_id: str) -> None:
        """Bind to the entry whose fingerprint devices hold the names."""
        self._hass = hass
        self._config_entry_id = config_entry_id

    def name_of(self, mac: str, record: LogEntry) -> str | None:
        """Return whose credential `record` was, or `None` when it is not known."""
        if record.record_type in FINGERPRINT_RECORD_TYPES:
            return self._fingerprint_name(mac, record.password)
        if record.record_type in BLE_APP_RECORD_TYPES and record.uid == 0:
            return HOME_ASSISTANT_NAME
        return None

    def _fingerprint_name(self, mac: str, credential: str | None) -> str | None:
        if credential is None or not credential.isdigit():
            return None
        fingerprint = TtlockBleEnrolledFingerprint.from_number(int(credential))
        if fingerprint is None:
            return None
        device = async_get_device_registry(
            self._hass
        ).async_get_child_device_by_identifier(
            fingerprint_identifier(mac, fingerprint), self._config_entry_id
        )
        if device is None:
            return None
        return device.name_by_user or device.name
