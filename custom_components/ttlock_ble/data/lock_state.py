"""Per-lock state surfaced by the coordinator."""

from __future__ import annotations

from typing import NotRequired, TypedDict


class TtlockBleLockState(TypedDict):
    """Per-lock state surfaced by the coordinator."""

    locked: NotRequired[bool | None]
    battery_level: NotRequired[int | None]
    available: bool
