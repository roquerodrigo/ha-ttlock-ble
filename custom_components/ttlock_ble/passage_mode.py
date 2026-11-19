"""Passage mode schedules: which slots cover a moment, and when that next changes."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING

from ttlock_ble import PassageModeSlot, PassageModeType

if TYPE_CHECKING:
    from .data import TtlockBlePassageSlotDescription

DAYS_PER_WEEK = 7
MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = 24 * MINUTES_PER_HOUR

# How far ahead to look for the next day a slot falls on: a weekly one
# comes round within the week, a monthly one within the year.
DAYS_AHEAD: dict[int, int] = {
    PassageModeType.WEEKLY: DAYS_PER_WEEK,
    PassageModeType.MONTHLY: 366,
}


def slot_covers(slot: PassageModeSlot, moment: datetime) -> bool:
    """Report whether `slot` is in effect at `moment`, in the lock's local time."""
    window = slot_next_window(slot, moment)
    return window is not None and window[0] <= moment


def slot_next_window(
    slot: PassageModeSlot,
    moment: datetime,
) -> tuple[datetime, datetime] | None:
    """
    Return the start and end of the occurrence in effect at `moment`, or the next.

    An end at midnight can only mean the end of the day, which is how an
    all-day slot is written. A kind this integration does not know has no
    occurrence.
    """
    midnight = datetime.combine(moment.date(), time.min, tzinfo=moment.tzinfo)
    for ahead in range(DAYS_AHEAD.get(slot.kind, -1) + 1):
        day = midnight + timedelta(days=ahead)
        if not _falls_on(slot, day):
            continue
        end = day + timedelta(minutes=slot.end_minute or MINUTES_PER_DAY)
        if end > moment:
            return day + timedelta(minutes=slot.start_minute), end
    return None


def _falls_on(slot: PassageModeSlot, day: datetime) -> bool:
    """Report whether `slot` recurs on `day`."""
    if slot.kind == PassageModeType.WEEKLY:
        return slot.day == day.isoweekday()
    return slot.day == day.day and slot.month in (0, day.month)


def window_in_effect(
    slots: list[PassageModeSlot],
    moment: datetime,
) -> tuple[datetime, datetime | None] | None:
    """
    Return when passage mode is, or next comes, into effect, and when it then ends.

    Slots that follow one another without a gap are one stretch: a window
    across midnight is two slots, and passage mode left on is seven. A
    stretch that runs the whole week round has no end.
    """
    windows = sorted(
        window
        for slot in slots
        if (window := slot_next_window(slot, moment)) is not None
    )
    if not windows:
        return None
    start, end = windows[0]
    limit = start + timedelta(days=DAYS_PER_WEEK)
    while end < limit:
        later = max(
            (
                window[1]
                for slot in slots
                if (window := slot_next_window(slot, end)) is not None
                and window[0] <= end
            ),
            default=end,
        )
        if later <= end:
            return start, end
        end = later
    return start, None


def next_transition(slots: list[PassageModeSlot], moment: datetime) -> datetime | None:
    """Return the next moment after `moment` at which any slot starts or ends."""
    boundaries = [
        boundary
        for slot in slots
        if (window := slot_next_window(slot, moment)) is not None
        for boundary in window
        if boundary > moment
    ]
    return min(boundaries, default=None)


def slots_for_schedule(
    start: time,
    end: time,
    days: list[int],
) -> list[PassageModeSlot]:
    """
    Return the weekly slots for a daily window from `start` to `end` on `days`.

    An end at midnight is the end of the day. A window that would run past
    midnight is refused: it is two slots on two days, and a schedule that
    reads "22:00 to 06:00" is more likely a mistake than a request.
    """
    start_minute = start.hour * MINUTES_PER_HOUR + start.minute
    end_minute = (end.hour * MINUTES_PER_HOUR + end.minute) or MINUTES_PER_DAY
    if end_minute <= start_minute:
        msg = f"The window {start:%H:%M} to {end:%H:%M} does not end after it starts"
        raise ValueError(msg)
    return [
        PassageModeSlot(
            kind=PassageModeType.WEEKLY,
            day=day,
            month=0,
            start_minute=start_minute,
            end_minute=end_minute,
        )
        for day in sorted(set(days))
    ]


def always_slots() -> list[PassageModeSlot]:
    """Return the slots that leave passage mode on: every weekday, all day."""
    return [
        PassageModeSlot(
            kind=PassageModeType.WEEKLY,
            day=day,
            month=0,
            start_minute=0,
            end_minute=MINUTES_PER_DAY,
        )
        for day in range(1, DAYS_PER_WEEK + 1)
    ]


def describe_slot(slot: PassageModeSlot) -> TtlockBlePassageSlotDescription:
    """Return `slot` as it is shown in a response or an attribute."""
    return {
        "kind": slot.kind,
        "day": slot.day,
        "month": slot.month,
        "start": _clock(slot.start_minute),
        "end": _clock(slot.end_minute),
    }


def slot_from_description(
    description: TtlockBlePassageSlotDescription,
) -> PassageModeSlot:
    """Rebuild a slot from the form `describe_slot` renders it in."""
    return PassageModeSlot(
        kind=description["kind"],
        day=description["day"],
        month=description["month"],
        start_minute=_minute(description["start"]),
        end_minute=_minute(description["end"]),
    )


def slot_to_record(slot: PassageModeSlot) -> list[int]:
    """Return the integers a slot is persisted as."""
    return [slot.kind, slot.day, slot.month, slot.start_minute, slot.end_minute]


def slot_from_record(record: list[int]) -> PassageModeSlot:
    """Rebuild a slot from the integers `slot_to_record` persisted."""
    kind, day, month, start_minute, end_minute = record
    return PassageModeSlot(kind, day, month, start_minute, end_minute)


def _clock(minute: int) -> str:
    """Render minutes since midnight as `HH:MM`."""
    return f"{minute // MINUTES_PER_HOUR:02d}:{minute % MINUTES_PER_HOUR:02d}"


def _minute(clock: str) -> int:
    """Read `HH:MM` back into minutes since midnight."""
    hour, minute = clock.split(":")
    return int(hour) * MINUTES_PER_HOUR + int(minute)
