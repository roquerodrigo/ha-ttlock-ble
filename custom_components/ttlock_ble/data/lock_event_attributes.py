"""Attributes published with a decoded operation-log event."""

from __future__ import annotations

from typing import NotRequired, TypedDict


class TtlockBleLogEventAttributes(TypedDict):
    """
    Attributes published with a decoded operation-log event.

    `credential` is the SDK's `password` field, which is only carried
    for record types where it identifies something (a card number, a
    fingerprint id, an accessory MAC). Record types where it is a
    working door code never populate it — see `PASSCODE_RECORD_TYPES`.
    """

    record_type: str
    battery: int
    timestamp: NotRequired[str]
    uid: NotRequired[int]
    credential: NotRequired[str]
    key_id: NotRequired[int]
    accessory_battery: NotRequired[int]
