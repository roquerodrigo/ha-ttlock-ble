"""Typed shape of a TTLock BLE passage mode schedule slot."""

from __future__ import annotations

from typing import TypedDict


class TtlockBlePassageSchedule(TypedDict):
    """A passage mode schedule slot for a TTLock smart lock."""

    type: int
    week_or_day: int
    month: int
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int
