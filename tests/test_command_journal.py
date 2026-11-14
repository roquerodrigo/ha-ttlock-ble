from __future__ import annotations

import datetime as dt

from custom_components.ttlock_ble.command_journal import (
    COMMAND_MATCH_TOLERANCE,
    TtlockBleCommandJournal,
)
from custom_components.ttlock_ble.data import TtlockBleIssuedCommand
from custom_components.ttlock_ble.lock_command import TtlockBleLockCommand

MAC = "AA:BB:CC:DD:EE:FF"
STARTED_AT = dt.datetime(2026, 10, 28, 10, 0, 0)  # noqa: DTZ001 — lock RTC is naive
CONFIRMED_AT = STARTED_AT + dt.timedelta(seconds=4)


def _issued(
    user_name: str | None = "Alice",
    *,
    command: TtlockBleLockCommand = TtlockBleLockCommand.UNLOCK,
    offset: dt.timedelta = dt.timedelta(),
) -> TtlockBleIssuedCommand:
    return TtlockBleIssuedCommand(
        command=command,
        started_at=STARTED_AT + offset,
        confirmed_at=CONFIRMED_AT + offset,
        user_name=user_name,
    )


def test_a_record_stamped_during_the_round_trip_is_of_that_command() -> None:
    journal = TtlockBleCommandJournal()
    journal.note(MAC, _issued())

    found = journal.find(
        MAC, TtlockBleLockCommand.UNLOCK, STARTED_AT + dt.timedelta(seconds=2)
    )

    assert found == _issued()


def test_a_drifted_stamp_still_matches_within_the_tolerance() -> None:
    journal = TtlockBleCommandJournal()
    journal.note(MAC, _issued())

    assert journal.find(
        MAC, TtlockBleLockCommand.UNLOCK, STARTED_AT - COMMAND_MATCH_TOLERANCE
    )
    assert journal.find(
        MAC, TtlockBleLockCommand.UNLOCK, CONFIRMED_AT + COMMAND_MATCH_TOLERANCE
    )


def test_a_stamp_outside_the_tolerance_matches_nothing() -> None:
    journal = TtlockBleCommandJournal()
    journal.note(MAC, _issued())
    second = dt.timedelta(seconds=1)

    assert (
        journal.find(
            MAC,
            TtlockBleLockCommand.UNLOCK,
            STARTED_AT - COMMAND_MATCH_TOLERANCE - second,
        )
        is None
    )
    assert (
        journal.find(
            MAC,
            TtlockBleLockCommand.UNLOCK,
            CONFIRMED_AT + COMMAND_MATCH_TOLERANCE + second,
        )
        is None
    )


def test_an_undated_record_matches_nothing() -> None:
    journal = TtlockBleCommandJournal()
    journal.note(MAC, _issued())

    assert journal.find(MAC, TtlockBleLockCommand.UNLOCK, None) is None


def test_the_other_command_and_another_lock_match_nothing() -> None:
    journal = TtlockBleCommandJournal()
    journal.note(MAC, _issued())

    assert journal.find(MAC, TtlockBleLockCommand.LOCK, CONFIRMED_AT) is None
    assert (
        journal.find("11:22:33:44:55:66", TtlockBleLockCommand.UNLOCK, CONFIRMED_AT)
        is None
    )


def test_the_closest_of_two_commands_wins() -> None:
    journal = TtlockBleCommandJournal()
    journal.note(MAC, _issued("Alice"))
    journal.note(MAC, _issued("Bob", offset=dt.timedelta(seconds=40)))

    early = journal.find(MAC, TtlockBleLockCommand.UNLOCK, CONFIRMED_AT)
    late = journal.find(
        MAC, TtlockBleLockCommand.UNLOCK, CONFIRMED_AT + dt.timedelta(seconds=38)
    )

    assert early is not None
    assert early.user_name == "Alice"
    assert late is not None
    assert late.user_name == "Bob"


def test_the_oldest_command_leaves_a_full_journal() -> None:
    journal = TtlockBleCommandJournal(window=1)
    journal.note(MAC, _issued("Alice"))
    journal.note(MAC, _issued("Bob", offset=dt.timedelta(hours=1)))

    assert journal.find(MAC, TtlockBleLockCommand.UNLOCK, CONFIRMED_AT) is None
