"""TtlockBleCredentialResolver — whose credential an operation record was."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ttlock_ble import LogOperate

from .credential_type import TtlockBleCredentialType
from .data import TtlockBleEnrolledFingerprint, TtlockBleLogCredential
from .data.known_credential import passcode_key

if TYPE_CHECKING:
    from ttlock_ble import LogEntry

    from .credential_store import TtlockBleCredentialStore

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

    def __init__(self, credentials: TtlockBleCredentialStore) -> None:
        """Bind to the store holding the names given to credentials."""
        self._credentials = credentials

    def resolve(self, mac: str, record: LogEntry) -> TtlockBleLogCredential:
        """Return what `record`, read from the lock `mac`, says about its credential."""
        credential_type = TtlockBleCredentialType.of_record(record.record_type)
        key = self._key_of(mac, credential_type, record.password)
        return TtlockBleLogCredential(
            credential_type=credential_type,
            identifier=self._identifier_of(mac, record, credential_type, key),
            name=self._name_of(mac, record, credential_type, key),
        )

    def _identifier_of(
        self,
        mac: str,
        record: LogEntry,
        credential_type: TtlockBleCredentialType | None,
        key: str | None,
    ) -> str | None:
        """
        Return what a record may show of its credential.

        A passcode shows only the label of one already known, never the
        code, and nothing at all for a code the lock refused.
        """
        if record.record_type not in PASSCODE_RECORD_TYPES:
            return record.password
        if credential_type is not TtlockBleCredentialType.PASSCODE or key is None:
            return None
        return self._credentials.label_of(mac, credential_type, key)

    def _name_of(
        self,
        mac: str,
        record: LogEntry,
        credential_type: TtlockBleCredentialType | None,
        key: str | None,
    ) -> str | None:
        if credential_type is not None and key is not None:
            return self._credentials.name_of(mac, credential_type, key)
        if record.record_type in BLE_APP_RECORD_TYPES and record.uid == 0:
            return HOME_ASSISTANT_NAME
        return None

    @staticmethod
    def _key_of(
        mac: str,
        credential_type: TtlockBleCredentialType | None,
        password: str | None,
    ) -> str | None:
        """Return the store key of the credential a record names, if it has one."""
        if not password:
            return None
        if credential_type is TtlockBleCredentialType.FINGERPRINT:
            if not password.isdigit():
                return None
            fingerprint = TtlockBleEnrolledFingerprint.from_number(int(password))
            return None if fingerprint is None else fingerprint.token
        if credential_type is TtlockBleCredentialType.CARD:
            return password
        if credential_type is TtlockBleCredentialType.PASSCODE:
            return passcode_key(mac, password)
        return None
