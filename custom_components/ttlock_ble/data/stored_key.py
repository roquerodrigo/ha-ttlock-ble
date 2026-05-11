"""`VirtualKey.to_dict()` shape persisted on the config entry."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from .stored_lock_version import TtlockBleStoredLockVersion


class TtlockBleStoredKey(TypedDict):
    """`VirtualKey.to_dict()` shape persisted on the config entry."""

    keyId: int
    lockId: int
    lockMac: str
    lockAlias: str
    lockName: str
    lockVersion: TtlockBleStoredLockVersion
    aesKeyStr: str
    unlockKey: str
    lockFlagPos: int
    timezoneRawOffSet: int
    startTime: int
    endTime: int
    keyType: int
    userType: str
    adminPs: str
    keyboardPwdVersion: int
    specialValue: int
    uid: int
