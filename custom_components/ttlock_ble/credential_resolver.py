"""TtlockBleCredentialResolver — whose credential an operation record was."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ttlock_ble import LogOperate

from .credential_type import TtlockBleCredentialType
from .data import TtlockBleEnrolledFingerprint, TtlockBleLogCredential

if TYPE_CHECKING:
    from ttlock_ble import LogEntry

    from .fingerprint_store import TtlockBleFingerprintStore

HOME_ASSISTANT_NAME = "Home Assistant"

# Record types whose `password` field is a working door code rather than an
# identifier. The SDK reuses one field for keypad codes, card numbers,
# fingerprint ids and fob MACs; only the first are secret, and an HA event
# or state attribute lands in the recorder database and is readable through
# the API by any user, so those never leave this module.
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


class TtlockBleCredentialResolver:
    """Tells the type, identifier and name of the credential behind a record."""

    def __init__(self, fingerprints: TtlockBleFingerprintStore) -> None:
        """Bind to the store holding the names given to fingerprints."""
        self._fingerprints = fingerprints

    def resolve(self, mac: str, record: LogEntry) -> TtlockBleLogCredential:
        """Return what `record`, read from the lock `mac`, says about its credential."""
        credential_type = TtlockBleCredentialType.of_record(record.record_type)
        identifier = (
            None if record.record_type in PASSCODE_RECORD_TYPES else record.password
        )
        return TtlockBleLogCredential(
            credential_type=credential_type,
            identifier=identifier,
            name=self._name_of(mac, record, credential_type, identifier),
        )

    def _name_of(
        self,
        mac: str,
        record: LogEntry,
        credential_type: TtlockBleCredentialType | None,
        identifier: str | None,
    ) -> str | None:
        if credential_type is TtlockBleCredentialType.FINGERPRINT:
            return self._fingerprint_name(mac, identifier)
        if record.record_type in BLE_APP_RECORD_TYPES and record.uid == 0:
            return HOME_ASSISTANT_NAME
        return None

    def _fingerprint_name(self, mac: str, identifier: str | None) -> str | None:
        if identifier is None or not identifier.isdigit():
            return None
        fingerprint = TtlockBleEnrolledFingerprint.from_number(int(identifier))
        if fingerprint is None:
            return None
        return self._fingerprints.name_of(mac, fingerprint)
