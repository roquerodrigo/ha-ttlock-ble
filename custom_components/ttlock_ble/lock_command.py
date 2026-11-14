"""TtlockBleLockCommand — what Home Assistant can ask of the bolt."""

from __future__ import annotations

from enum import StrEnum


class TtlockBleLockCommand(StrEnum):
    """A bolt command sent over BLE on behalf of Home Assistant."""

    LOCK = "lock"
    UNLOCK = "unlock"
