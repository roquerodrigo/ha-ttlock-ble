"""A bolt command Home Assistant sent to a lock."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from ..lock_command import TtlockBleLockCommand


@dataclass(frozen=True)
class TtlockBleIssuedCommand:
    """
    One command the lock confirmed, and who asked Home Assistant for it.

    The times are naive local ones, as the lock stamps its records, and
    bound the round trip: the lock executed the command somewhere between
    them. `user_name` is `None` when no person was behind the call, as
    for an automation.
    """

    command: TtlockBleLockCommand
    started_at: datetime
    confirmed_at: datetime
    user_name: str | None
