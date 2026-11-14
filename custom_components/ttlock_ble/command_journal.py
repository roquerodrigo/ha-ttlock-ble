"""TtlockBleCommandJournal — the commands Home Assistant sent to each lock."""

from __future__ import annotations

from collections import deque
from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from .data import TtlockBleIssuedCommand
    from .lock_command import TtlockBleLockCommand

# Enough for every command whose record may still be unread.
COMMAND_JOURNAL_WINDOW = 16

# How far a record's stamp may fall outside the round trip of the command
# it is matched to. The stamp comes from the lock's own clock, which is
# only corrected once it has drifted by more than
# `CLOCK_DRIFT_THRESHOLD_SECONDS`.
COMMAND_MATCH_TOLERANCE = timedelta(seconds=60)


class TtlockBleCommandJournal:
    """
    Recent commands sent to each lock, to tell their records from an app's.

    The lock files a command from this integration under the same record
    type and user id as one from the official app signed in to the same
    account, so the record alone cannot say which of the two it was. What
    can is that a command was sent at the moment the record is stamped.

    Kept in memory only: a record is read seconds after its command.
    """

    def __init__(self, window: int = COMMAND_JOURNAL_WINDOW) -> None:
        """Start with no commands noted."""
        self._window = window
        self._commands: dict[str, deque[TtlockBleIssuedCommand]] = {}

    def note(self, mac: str, command: TtlockBleIssuedCommand) -> None:
        """Remember a command the lock `mac` confirmed."""
        self._commands.setdefault(mac, deque(maxlen=self._window)).append(command)

    def find(
        self,
        mac: str,
        command: TtlockBleLockCommand,
        stamped_at: datetime | None,
    ) -> TtlockBleIssuedCommand | None:
        """Return the `command` sent to `mac` that a record stamped then is of."""
        if stamped_at is None:
            return None
        candidates = [
            issued
            for issued in self._commands.get(mac, ())
            if issued.command is command
            and issued.started_at - COMMAND_MATCH_TOLERANCE
            <= stamped_at
            <= issued.confirmed_at + COMMAND_MATCH_TOLERANCE
        ]
        return min(
            candidates,
            key=lambda issued: abs(issued.confirmed_at - stamped_at),
            default=None,
        )
