"""Which lock settings a `VirtualKey` is allowed to touch, and what it may find."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ttlock_ble import LockFeature

if TYPE_CHECKING:
    from ttlock_ble import VirtualKey


def can_administer(key: VirtualKey) -> bool:
    """
    Report whether `key` may read or change lock settings at all.

    The firmware gates settings behind CHECK_ADMIN, which needs both an
    admin key and the admin passcode that authorises it. A key obtained
    outside a TTLock account often carries no passcode, and a request
    that can only ever fail is not worth a BLE round trip.
    """
    return key.is_admin() and bool(key.adminPs)


def may_hold(key: VirtualKey, feature: LockFeature) -> bool:
    """
    Report whether the lock behind `key` may hold a kind of credential.

    A key carrying no feature bits at all, as a manually entered one
    does, says nothing either way, so it is not taken as a refusal.
    """
    return key.feature_mask == 0 or key.has_feature(feature)


def can_manage_passage_mode(key: VirtualKey) -> bool:
    """
    Report whether the lock behind `key` can be asked about its passage mode.

    The firmware lists and changes the slots only for an admin key, and a
    lock whose feature bits rule passage mode out has none to list.
    """
    return can_administer(key) and may_hold(key, LockFeature.PASSAGE_MODE)
