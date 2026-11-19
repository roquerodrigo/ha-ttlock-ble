from __future__ import annotations

from datetime import UTC, datetime, time

import pytest
from ttlock_ble import PassageModeSlot, PassageModeType

from custom_components.ttlock_ble.passage_mode import (
    always_slots,
    describe_slot,
    next_transition,
    slot_covers,
    slot_from_description,
    slot_from_record,
    slot_next_window,
    slot_to_record,
    slots_for_schedule,
    window_in_effect,
)

# 2026-11-14 is a Saturday.
SLOT = PassageModeSlot(
    kind=PassageModeType.WEEKLY, day=6, month=0, start_minute=1335, end_minute=1350
)


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def _weekly(day: int, start: int, end: int) -> PassageModeSlot:
    return PassageModeSlot(
        kind=PassageModeType.WEEKLY,
        day=day,
        month=0,
        start_minute=start,
        end_minute=end,
    )


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (_at(14, 22, 15), True),
        (_at(14, 22, 29), True),
        (_at(14, 22, 30), False),
        (_at(15, 22, 15), False),
    ],
)
def test_a_weekly_slot_covers_its_window(moment, expected) -> None:
    assert slot_covers(SLOT, moment) is expected


def test_a_slot_ending_at_midnight_runs_to_the_end_of_the_day() -> None:
    assert slot_covers(_weekly(6, 0, 0), _at(14, 23, 59))


def test_a_slot_ending_at_24_00_runs_to_the_end_of_the_day() -> None:
    assert slot_covers(_weekly(6, 0, 1440), _at(14, 23, 59))


@pytest.mark.parametrize(
    ("month", "expected"),
    [(0, True), (11, True), (3, False)],
)
def test_a_monthly_slot_covers_its_day(month, expected) -> None:
    slot = PassageModeSlot(
        kind=PassageModeType.MONTHLY,
        day=14,
        month=month,
        start_minute=0,
        end_minute=1440,
    )
    assert slot_covers(slot, _at(14, 12)) is expected


def test_a_kind_nobody_knows_is_never_in_effect() -> None:
    slot = PassageModeSlot(kind=9, day=6, month=0, start_minute=0, end_minute=1440)
    assert slot_next_window(slot, _at(14, 12)) is None
    assert not slot_covers(slot, _at(14, 12))


def test_the_next_window_of_a_slot_that_ended_is_a_week_on() -> None:
    assert slot_next_window(SLOT, _at(14, 22, 30)) == (_at(21, 22, 15), _at(21, 22, 30))


def test_the_window_in_effect_is_the_slot_covering_now() -> None:
    assert window_in_effect([SLOT], _at(14, 22, 20)) == (
        _at(14, 22, 15),
        _at(14, 22, 30),
    )


def test_no_slot_means_no_window() -> None:
    assert window_in_effect([], _at(14, 12)) is None


def test_the_earliest_of_several_slots_is_the_next_window() -> None:
    slots = [_weekly(1, 540, 1020), _weekly(7, 600, 660)]
    assert window_in_effect(slots, _at(14, 23)) == (_at(15, 10), _at(15, 11))


def test_slots_that_follow_one_another_are_one_window() -> None:
    """A window across midnight is two slots and one stretch of passage mode."""
    slots = [_weekly(6, 1410, 1440), _weekly(7, 0, 45)]
    assert window_in_effect(slots, _at(14, 23, 40)) == (_at(14, 23, 30), _at(15, 0, 45))


def test_passage_mode_left_on_has_no_end() -> None:
    start, end = window_in_effect(always_slots(), _at(14, 12))
    assert start == _at(14, 0)
    assert end is None


def test_the_next_transition_of_a_slot_in_effect_is_its_end() -> None:
    assert next_transition([SLOT], _at(14, 22, 20)) == _at(14, 22, 30)


def test_the_next_transition_before_a_slot_is_its_start() -> None:
    assert next_transition([SLOT], _at(14, 20)) == _at(14, 22, 15)


def test_the_next_transition_is_the_earliest_across_slots() -> None:
    assert next_transition([SLOT, _weekly(6, 1300, 1310)], _at(14, 21, 30)) == _at(
        14, 21, 40
    )


def test_no_slot_means_no_transition() -> None:
    assert next_transition([], _at(14, 12)) is None


def test_a_schedule_is_one_slot_per_day() -> None:
    slots = slots_for_schedule(time(9, 0), time(17, 30), [3, 1, 3])
    assert slots == [_weekly(1, 540, 1050), _weekly(3, 540, 1050)]


def test_a_schedule_ending_at_midnight_runs_to_the_end_of_the_day() -> None:
    assert slots_for_schedule(time(22, 0), time(0, 0), [6]) == [_weekly(6, 1320, 1440)]


@pytest.mark.parametrize(
    ("start", "end"),
    [(time(17, 0), time(9, 0)), (time(9, 0), time(9, 0))],
)
def test_a_schedule_that_does_not_end_after_it_starts_is_refused(start, end) -> None:
    with pytest.raises(ValueError, match="does not end"):
        slots_for_schedule(start, end, [1])


def test_always_slots_cover_every_weekday_all_day() -> None:
    slots = always_slots()
    assert [slot.day for slot in slots] == [1, 2, 3, 4, 5, 6, 7]
    assert {(slot.start_minute, slot.end_minute) for slot in slots} == {(0, 1440)}


def test_a_slot_round_trips_through_its_description() -> None:
    description = describe_slot(SLOT)
    assert description == {
        "kind": 1,
        "day": 6,
        "month": 0,
        "start": "22:15",
        "end": "22:30",
    }
    assert slot_from_description(description) == SLOT


def test_a_slot_round_trips_through_its_record() -> None:
    assert slot_from_record(slot_to_record(SLOT)) == SLOT
