"""What the last comparison of a lock's clock against Home Assistant's found."""

from __future__ import annotations

from typing import TypedDict


class TtlockBleClockSync(TypedDict):
    """
    Outcome of the last comparison between a lock's RTC and local time.

    `drift_seconds` is what the lock was off by *before* any correction,
    positive when it ran ahead. It is kept as measured rather than reset
    to zero after a calibration, because the useful question is how far
    the clock had wandered — a lock that needs a minute put back on it
    every day is a lock whose records are worth doubting.

    `checked_at` is when the comparison ran, not when a correction was
    written: a lock whose clock was already close is checked and left
    alone, and that still counts as knowing where it stands.
    """

    checked_at: str
    drift_seconds: float
