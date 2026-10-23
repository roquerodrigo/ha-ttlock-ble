"""Per-lock state surfaced by the coordinator."""

from __future__ import annotations

from typing import NotRequired, TypedDict


class TtlockBleLockState(TypedDict):
    """
    Per-lock state surfaced by the coordinator.

    There is deliberately no reachability flag here. A TTLock drops the
    BLE session within seconds of going idle, so a poll that found
    nothing is the normal resting state of a healthy lock, not evidence
    that it is gone — an entity marked unavailable on that basis would
    blank itself right after every successful command. Entities keep the
    last known values instead, and the connectivity binary sensor is
    what reports the live link.
    """

    locked: NotRequired[bool | None]
    battery_level: NotRequired[int | None]
    # `time.monotonic()` at the moment `locked` was read off the lock, not
    # when it was published. A poll reads the bolt the instant a command
    # returns and publishes it seconds later, so only the read time says
    # whether the value predates the bolt finishing its travel.
    observed_at: NotRequired[float | None]
