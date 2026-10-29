from __future__ import annotations

import pytest
from ttlock_ble import LogOperate

from custom_components.ttlock_ble.credential_type import (
    _RECORD_TYPES_BY_CREDENTIAL,
    TtlockBleCredentialType,
)


@pytest.mark.parametrize(
    ("record_type", "expected"),
    [
        (LogOperate.FR_UNLOCK_SUCCEED, TtlockBleCredentialType.FINGERPRINT),
        (LogOperate.IC_UNLOCK_SUCCEED, TtlockBleCredentialType.CARD),
        (LogOperate.KEYBOARD_PASSWORD_UNLOCK, TtlockBleCredentialType.PASSCODE),
        (LogOperate.ADMIN_CODE_UNLOCK, TtlockBleCredentialType.PASSCODE),
        (LogOperate.MOBILE_UNLOCK, TtlockBleCredentialType.APP),
        (LogOperate.GATEWAY_UNLOCK, TtlockBleCredentialType.GATEWAY),
        (LogOperate.WIRELESS_KEY_FOB, TtlockBleCredentialType.KEY_FOB),
        (LogOperate.WIRELESS_KEY_PAD, TtlockBleCredentialType.WIRELESS_KEYPAD),
        (LogOperate.OPERATE_KEY_UNLOCK, TtlockBleCredentialType.MECHANICAL_KEY),
        (LogOperate.FACE_3D_UNLOCK_SUCCESS, TtlockBleCredentialType.FACE),
        (LogOperate.PALM_VEIN_UNLOCK_SUCCESS, TtlockBleCredentialType.PALM_VEIN),
        (LogOperate.QR_CODE_UNLOCK_SUCCESS, TtlockBleCredentialType.QR_CODE),
        (LogOperate.DOOR_REBOOT, None),
        (9999, None),
    ],
)
def test_a_record_names_its_credential_type(record_type, expected) -> None:
    assert TtlockBleCredentialType.of_record(record_type) is expected


def test_every_credential_type_has_its_records() -> None:
    assert set(_RECORD_TYPES_BY_CREDENTIAL) == set(TtlockBleCredentialType)


def test_no_record_type_belongs_to_two_credentials() -> None:
    groups = list(_RECORD_TYPES_BY_CREDENTIAL.values())
    for index, first in enumerate(groups):
        for second in groups[index + 1 :]:
            assert first & second == frozenset()


def test_every_passcode_record_is_withheld() -> None:
    """A record typed as a passcode carries the code, so it must be redacted."""
    from custom_components.ttlock_ble.credential_resolver import (
        PASSCODE_RECORD_TYPES,
    )

    assert _RECORD_TYPES_BY_CREDENTIAL[TtlockBleCredentialType.PASSCODE] <= (
        PASSCODE_RECORD_TYPES
    )
