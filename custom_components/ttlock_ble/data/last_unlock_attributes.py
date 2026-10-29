"""Attributes of the sensor naming who last unlocked a lock."""

from __future__ import annotations

from typing import NotRequired, TypedDict


class TtlockBleLastUnlockAttributes(TypedDict):
    """The credential behind the last unlock, and when the lock recorded it."""

    credential_type: NotRequired[str]
    credential: NotRequired[str]
    unlocked_at: NotRequired[str]
