"""Where a lock's operation log was last read, handed to its connection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True, slots=True)
class TtlockBleLogCursor:
    """
    A lock's place in its operation log, restored from a previous run.

    `seeded` is carried separately from `records` because the two are
    not the same fact: a lock whose log was already synced seeds an
    empty set, and an empty set is indistinguishable from never having
    looked. Without the flag such a lock repeats its backlog pass after
    every restart and keeps swallowing its first real record.

    `on_move` is called with the full set whenever it grows, so the
    caller can persist it.
    """

    records: set[int] = field(default_factory=set)
    seeded: bool = False
    on_move: Callable[[set[int]], None] | None = None
