"""A passage mode slot as it is shown to the user."""

from __future__ import annotations

from typing import TypedDict


class TtlockBlePassageSlotDescription(TypedDict):
    """One slot, with its times as `HH:MM` instead of minutes since midnight."""

    kind: int
    day: int
    month: int
    start: str
    end: str
