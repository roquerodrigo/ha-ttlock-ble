"""Unit tests for Passage Mode Active binary sensor and Schedule sensor."""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ttlock_ble.binary_sensor import (
    TtlockBlePassageModeActiveBinarySensor,
    get_next_passage_mode_transition,
    is_passage_mode_active,
)
from custom_components.ttlock_ble.button import TtlockBleSyncPassageModeButton
from custom_components.ttlock_ble.sensor import (
    TtlockBlePassageModeScheduleSensor,
    format_passage_mode_status,
    get_passage_schedule_attributes,
)


def test_is_passage_mode_active() -> None:
    """Test passage mode active evaluation based on day and time."""
    # 2026-09-07 is a Monday (isoweekday = 1)
    mon_10am = dt.datetime(2026, 9, 7, 10, 0, 0)
    mon_07am = dt.datetime(2026, 9, 7, 7, 0, 0)
    mon_17pm = dt.datetime(2026, 9, 7, 17, 30, 0)
    tue_10am = dt.datetime(2026, 9, 8, 10, 0, 0)

    # Empty schedules
    assert not is_passage_mode_active([], mon_10am)

    # Weekly Monday 08:00 to 17:00
    schedules = [{
        "type": 1,
        "week_or_day": 1,
        "month": 0,
        "start_hour": 8,
        "start_minute": 0,
        "end_hour": 17,
        "end_minute": 0,
    }]

    assert is_passage_mode_active(schedules, mon_10am)
    assert not is_passage_mode_active(schedules, mon_07am)
    assert not is_passage_mode_active(schedules, mon_17pm)
    assert not is_passage_mode_active(schedules, tue_10am)


def test_get_next_passage_mode_transition() -> None:
    """Test calculating exact next transition point without polling."""
    # Monday 2026-09-07
    schedules = [{
        "type": 1,
        "week_or_day": 1,
        "month": 0,
        "start_hour": 8,
        "start_minute": 0,
        "end_hour": 17,
        "end_minute": 0,
    }]

    # Before start -> next transition is 08:00 today
    now = dt.datetime(2026, 9, 7, 7, 30, 0)
    nxt = get_next_passage_mode_transition(schedules, now)
    assert nxt == dt.datetime(2026, 9, 7, 8, 0, 0)

    # During active -> next transition is 17:00 today
    now = dt.datetime(2026, 9, 7, 10, 0, 0)
    nxt = get_next_passage_mode_transition(schedules, now)
    assert nxt == dt.datetime(2026, 9, 7, 17, 0, 0)

    # After end -> next transition is 08:00 next Monday
    now = dt.datetime(2026, 9, 7, 18, 0, 0)
    nxt = get_next_passage_mode_transition(schedules, now)
    assert nxt == dt.datetime(2026, 9, 14, 8, 0, 0)


def test_format_passage_mode_status() -> None:
    """Test dynamic meaningful passage schedule status."""
    assert format_passage_mode_status([], dt.datetime.now()) == "No schedule"

    # Wednesday 2026-09-09
    wed_12pm = dt.datetime(2026, 9, 9, 12, 5, 0)
    wed_1330 = dt.datetime(2026, 9, 9, 13, 30, 0)
    wed_23pm = dt.datetime(2026, 9, 9, 23, 0, 0)

    # Friday slot + Everyday (0) slots like user's exact schedule
    schedules = [
        {"type": 1, "week_or_day": 5, "start_hour": 13, "start_minute": 0, "end_hour": 15, "end_minute": 0},  # Fri
        {"type": 1, "week_or_day": 0, "start_hour": 5, "start_minute": 0, "end_hour": 6, "end_minute": 0},    # Everyday 05:00
        {"type": 1, "week_or_day": 0, "start_hour": 13, "start_minute": 15, "end_hour": 14, "end_minute": 0}, # Everyday 13:15
        {"type": 1, "week_or_day": 0, "start_hour": 16, "start_minute": 25, "end_hour": 17, "end_minute": 15}, # Everyday 16:25
    ]

    # At 12:05 on Wednesday -> next is Today 13:15
    assert format_passage_mode_status(schedules, wed_12pm) == "Next: Today 13:15"

    # At 13:30 on Wednesday -> active until 14:00
    assert format_passage_mode_status(schedules, wed_1330) == "Active (until 14:00)"

    # At 23:00 on Wednesday -> next is Tomorrow 05:00
    assert format_passage_mode_status(schedules, wed_23pm) == "Next: Tomorrow 05:00"


def test_get_passage_schedule_attributes() -> None:
    """Test schedule attributes include today_slots and active_slot."""
    # Wednesday 2026-09-09 13:30
    wed_1330 = dt.datetime(2026, 9, 9, 13, 30, 0)
    schedules = [
        {"type": 1, "week_or_day": 3, "start_hour": 5, "start_minute": 0, "end_hour": 6, "end_minute": 0},
        {"type": 1, "week_or_day": 3, "start_hour": 13, "start_minute": 15, "end_hour": 14, "end_minute": 0},
        {"type": 1, "week_or_day": 5, "start_hour": 13, "start_minute": 0, "end_hour": 15, "end_minute": 0},
    ]
    attrs = get_passage_schedule_attributes(schedules, wed_1330)
    assert attrs["today_slots"] == ["05:00-06:00", "13:15-14:00"]
    assert attrs["active_slot"] == {"start_time": "13:15", "end_time": "14:00"}
    assert attrs["schedule_count"] == 3


@pytest.mark.asyncio
async def test_passage_mode_entities() -> None:
    """Test passage mode binary sensor, sensor, and sync button."""
    coordinator = MagicMock()
    key = MagicMock()
    key.lockMac = "AA:BB:CC:DD:EE:FF"

    connection = MagicMock()
    connection.passage_schedules = [{
        "type": 1,
        "week_or_day": 1,
        "month": 0,
        "start_hour": 0,
        "start_minute": 0,
        "end_hour": 0,
        "end_minute": 1,
    }]
    connection.async_get_passage_mode = AsyncMock(return_value=[])

    # Binary sensor
    bs = TtlockBlePassageModeActiveBinarySensor(coordinator, key, connection)
    assert bs.unique_id == "AA:BB:CC:DD:EE:FF_passage_mode_active"
    attrs = bs.extra_state_attributes
    assert attrs["schedule_count"] == 1
    assert attrs["has_schedule"] is True
    assert len(attrs["schedules"]) == 1
    assert attrs["schedules"][0]["day"] == "monday"

    # Schedule sensor
    sensor = TtlockBlePassageModeScheduleSensor(coordinator, key, connection)
    assert sensor.unique_id == "AA:BB:CC:DD:EE:FF_passage_mode_schedule"
    assert isinstance(sensor.native_value, str)

    # Sync button
    btn = TtlockBleSyncPassageModeButton(coordinator, key, connection)
    assert btn.unique_id == "AA:BB:CC:DD:EE:FF_sync_passage_mode"
    await btn.async_press()
    connection.async_get_passage_mode.assert_awaited_once()
