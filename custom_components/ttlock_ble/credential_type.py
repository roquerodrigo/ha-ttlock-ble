"""TtlockBleCredentialType — what kind of credential an operation record used."""

from __future__ import annotations

from enum import StrEnum

from ttlock_ble import LogOperate


class TtlockBleCredentialType(StrEnum):
    """The credential a log record was made with, as a stable event value."""

    FINGERPRINT = "fingerprint"
    CARD = "card"
    PASSCODE = "passcode"
    APP = "app"
    GATEWAY = "gateway"
    KEY_FOB = "key_fob"
    WIRELESS_KEYPAD = "wireless_keypad"
    MECHANICAL_KEY = "mechanical_key"
    FACE = "face"
    PALM_VEIN = "palm_vein"
    QR_CODE = "qr_code"

    @classmethod
    def of_record(cls, record_type: int) -> TtlockBleCredentialType | None:
        """Return the credential `record_type` names, or `None` for none."""
        for credential_type, record_types in _RECORD_TYPES_BY_CREDENTIAL.items():
            if record_type in record_types:
                return credential_type
        return None


_RECORD_TYPES_BY_CREDENTIAL: dict[TtlockBleCredentialType, frozenset[int]] = {
    TtlockBleCredentialType.FINGERPRINT: frozenset(
        {
            LogOperate.FR_UNLOCK_SUCCEED,
            LogOperate.FR_UNLOCK_FAILED,
            LogOperate.FR_LOCK,
            LogOperate.FR_UNLOCK_FAILED_LOCK_REVERSE,
            LogOperate.DOUBLE_CHECK_FINGER_PRINT_UNLOCK,
            LogOperate.ADD_FR,
            LogOperate.DELETE_FR_SUCCEED,
            LogOperate.CLEAR_FR_SUCCEED,
        },
    ),
    TtlockBleCredentialType.CARD: frozenset(
        {
            LogOperate.IC_UNLOCK_SUCCEED,
            LogOperate.IC_UNLOCK_FAILED,
            LogOperate.IC_LOCK,
            LogOperate.IC_UNLOCK_FAILED_LOCK_REVERSE,
            LogOperate.IC_UNLOCK_FAILED_BLACKLIST,
            LogOperate.DOUBLE_CHECK_CARD_UNLOCK,
            LogOperate.CPU_CARD_UNLOCK_FAILED,
            LogOperate.CARD_UNLOCK_FAILED,
            LogOperate.ADD_IC,
            LogOperate.DELETE_IC_SUCCEED,
            LogOperate.CLEAR_IC_SUCCEED,
        },
    ),
    TtlockBleCredentialType.PASSCODE: frozenset(
        {
            LogOperate.KEYBOARD_PASSWORD_UNLOCK,
            LogOperate.ERROR_PASSWORD_UNLOCK,
            LogOperate.PASSCODE_LOCK,
            LogOperate.PASSCODE_UNLOCK_FAILED_LOCK_REVERSE,
            LogOperate.DOUBLE_CHECK_PASSCODE_UNLOCK,
            LogOperate.ADMIN_CODE_UNLOCK,
            LogOperate.PASSCODE_EXPIRED,
            LogOperate.PASSCODE_IN_BLACK_LIST,
            LogOperate.KEYBOARD_MODIFY_PASSWORD,
            LogOperate.KEYBOARD_REMOVE_SINGLE_PASSWORD,
            LogOperate.KEYBOARD_REMOVE_ALL_PASSWORDS,
            LogOperate.KEYBOARD_PASSWORD_KICKED,
            LogOperate.USE_DELETE_CODE,
            LogOperate.ADD_PASSCODE_SUCCESSFULLY,
        },
    ),
    TtlockBleCredentialType.APP: frozenset(
        {
            LogOperate.MOBILE_UNLOCK,
            LogOperate.OPERATE_BLE_LOCK,
            LogOperate.APP_UNLOCK_FAILED_LOCK_REVERSE,
            LogOperate.APP_DEAD_LOCK,
            LogOperate.APP_AUTH_KEY_UNLOCK_SUCCESS,
        },
    ),
    TtlockBleCredentialType.GATEWAY: frozenset(
        {
            LogOperate.SERVER_UNLOCK,
            LogOperate.GATEWAY_UNLOCK,
            LogOperate.GATEWAY_AUTH_KEY_UNLOCK_SUCCESS,
        },
    ),
    TtlockBleCredentialType.KEY_FOB: frozenset(
        {
            LogOperate.WIRELESS_KEY_FOB,
            LogOperate.REMOTE_CONTROL_KEY,
            LogOperate.DOUBLE_CHECK_KEY_FOB_UNLOCK,
        },
    ),
    TtlockBleCredentialType.WIRELESS_KEYPAD: frozenset({LogOperate.WIRELESS_KEY_PAD}),
    TtlockBleCredentialType.MECHANICAL_KEY: frozenset(
        {LogOperate.OPERATE_KEY_UNLOCK, LogOperate.OPERATE_KEY_LOCK},
    ),
    TtlockBleCredentialType.FACE: frozenset(
        {
            LogOperate.FACE_3D_UNLOCK_SUCCESS,
            LogOperate.FACE_3D_UNLOCK_FAILED_LOCK_REVERSE,
            LogOperate.FACE_3D_UNLOCK_FAILED_INVALID_TIME,
            LogOperate.FACE_3D_LOCK,
            LogOperate.DOUBLE_CHECK_FACE_UNLOCK,
            LogOperate.FACE_3D_ADD_SUCCESS,
            LogOperate.FACE_3D_DELETE_SUCCESS,
            LogOperate.FACE_3D_CLEAR_SUCCESS,
        },
    ),
    TtlockBleCredentialType.PALM_VEIN: frozenset(
        {
            LogOperate.PALM_VEIN_UNLOCK_SUCCESS,
            LogOperate.PALM_VEIN_UNLOCK_FAILED,
            LogOperate.PALM_VEIN_UNLOCK_FAILED_LOCK_REVERSE,
            LogOperate.PALM_VEIN_LOCK,
            LogOperate.DOUBLE_CHECK_PALM_VEIN_UNLOCK,
            LogOperate.PALM_VEIN_ADD_SUCCESS,
            LogOperate.PALM_VEIN_DELETE_SUCCESS,
            LogOperate.PALM_VEIN_CLEAR_SUCCESS,
        },
    ),
    TtlockBleCredentialType.QR_CODE: frozenset(
        {
            LogOperate.QR_CODE_UNLOCK_SUCCESS,
            LogOperate.QR_CODE_UNLOCK_FAILED,
            LogOperate.QR_CODE_LOCK_SUCCESS,
            LogOperate.QR_CODE_UNLOCK_FAILED_LOCK_REVERSE,
        },
    ),
}
