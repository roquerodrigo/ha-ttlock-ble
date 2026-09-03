"""Tests for TTLock BLE passage mode protocol, serialization, and helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from ttlock_ble import TTLockError
from ttlock_ble.constants import ResponseStatus
from ttlock_ble.protocol import Frame

from custom_components.ttlock_ble.data import TtlockBlePassageSchedule
from custom_components.ttlock_ble.passage import (
    CMD_CONFIGURE_PASSAGE_MODE,
    PASSAGE_MODE_ADD,
    PASSAGE_MODE_CLEAR,
    PASSAGE_MODE_DELETE,
    PASSAGE_MODE_QUERY,
    PASSAGE_TYPE_MONTHLY,
    PASSAGE_TYPE_WEEKLY,
    async_client_clear_passage_mode,
    async_client_delete_passage_mode,
    async_client_get_passage_mode,
    async_client_set_passage_mode,
    build_passage_clear_payload,
    build_passage_delete_payload,
    build_passage_query_payload,
    build_passage_set_payload,
    parse_passage_query_response,
)
from custom_components.ttlock_ble.services import (
    _parse_days,
    _parse_schedules_from_call,
    _parse_single_slot,
    _parse_time_component,
)


def test_build_passage_query_payload() -> None:
    """Test building a query payload."""
    payload = build_passage_query_payload()
    assert payload == bytes([PASSAGE_MODE_QUERY, 0x00])

    payload_seq = build_passage_query_payload(sequence=5)
    assert payload_seq == bytes([PASSAGE_MODE_QUERY, 0x05])


def test_build_passage_clear_payload() -> None:
    """Test building a clear payload."""
    payload = build_passage_clear_payload()
    assert payload == bytes([PASSAGE_MODE_CLEAR])


def test_build_passage_set_payload_valid() -> None:
    """Test building a valid set payload."""
    schedule: TtlockBlePassageSchedule = {
        "type": PASSAGE_TYPE_WEEKLY,
        "week_or_day": 1,
        "month": 0,
        "start_hour": 8,
        "start_minute": 30,
        "end_hour": 17,
        "end_minute": 0,
    }
    payload = build_passage_set_payload(schedule)
    assert payload == bytes([
        PASSAGE_MODE_ADD,
        0x01,  # type: weekly
        0x01,  # Monday
        0x00,  # month 0
        0x08,  # 8 AM
        0x1E,  # 30 min
        0x11,  # 17 (5 PM)
        0x00,  # 0 min
    ])


def test_build_passage_set_payload_validation_errors() -> None:
    """Test validation errors for invalid hours, minutes, and day."""
    with pytest.raises(ValueError, match="Invalid start time"):
        build_passage_set_payload({
            "type": PASSAGE_TYPE_WEEKLY,
            "week_or_day": 1,
            "month": 0,
            "start_hour": 24,
            "start_minute": 0,
            "end_hour": 17,
            "end_minute": 0,
        })

    with pytest.raises(ValueError, match="Invalid end time"):
        build_passage_set_payload({
            "type": PASSAGE_TYPE_WEEKLY,
            "week_or_day": 1,
            "month": 0,
            "start_hour": 8,
            "start_minute": 0,
            "end_hour": 17,
            "end_minute": 60,
        })

    with pytest.raises(ValueError, match="Invalid week_or_day"):
        build_passage_set_payload({
            "type": PASSAGE_TYPE_WEEKLY,
            "week_or_day": 8,
            "month": 0,
            "start_hour": 8,
            "start_minute": 0,
            "end_hour": 17,
            "end_minute": 0,
        })


def test_build_passage_delete_payload() -> None:
    """Test building a delete payload."""
    schedule: TtlockBlePassageSchedule = {
        "type": PASSAGE_TYPE_WEEKLY,
        "week_or_day": 5,
        "month": 0,
        "start_hour": 9,
        "start_minute": 15,
        "end_hour": 18,
        "end_minute": 45,
    }
    payload = build_passage_delete_payload(schedule)
    assert payload == bytes([
        PASSAGE_MODE_DELETE,
        0x01,
        0x05,
        0x00,
        0x09,
        0x0F,
        0x12,
        0x2D,
    ])


def test_parse_passage_query_response() -> None:
    """Test parsing empty and multiple schedule slots from response data."""
    assert parse_passage_query_response(b"") == (0, [])
    assert parse_passage_query_response(bytes([0x01])) == (0, [])
    assert parse_passage_query_response(bytes([0x50, 0x01, 0x00])) == (0, [])

    # Two slots: battery=80, opType=1, sequence=0
    # Monday 08:30–12:00 and Monday 14:00–18:00
    data = bytes([
        0x50,  # battery=80%
        0x01,  # opType=1
        0x00,  # sequence=0 (done)
        0x01,
        0x01,
        0x00,
        0x08,
        0x1E,
        0x0C,
        0x00,  # slot 1
        0x01,
        0x01,
        0x00,
        0x0E,
        0x00,
        0x12,
        0x00,  # slot 2
    ])
    next_seq, schedules = parse_passage_query_response(data)
    assert next_seq == 0
    assert len(schedules) == 2
    assert schedules[0] == {
        "type": PASSAGE_TYPE_WEEKLY,
        "week_or_day": 1,
        "month": 0,
        "start_hour": 8,
        "start_minute": 30,
        "end_hour": 12,
        "end_minute": 0,
    }
    assert schedules[1] == {
        "type": PASSAGE_TYPE_WEEKLY,
        "week_or_day": 1,
        "month": 0,
        "start_hour": 14,
        "start_minute": 0,
        "end_hour": 18,
        "end_minute": 0,
    }


def test_parse_time_component() -> None:
    """Test time string parsing."""
    import datetime as dt

    assert _parse_time_component("08:30") == (8, 30)
    assert _parse_time_component("23:59") == (23, 59)
    assert _parse_time_component("00:00") == (0, 0)
    assert _parse_time_component(dt.time(14, 45)) == (14, 45)


def test_parse_days() -> None:
    """Test parsing day representations."""
    assert _parse_days("mon") == [1]
    assert _parse_days("monday") == [1]
    assert _parse_days("fri") == [5]
    assert _parse_days("sunday") == [7]
    assert _parse_days("everyday") == [0]
    assert _parse_days("all") == [0]
    assert _parse_days(3) == [3]
    assert _parse_days(["mon", "wed", "fri"]) == [1, 3, 5]


def test_parse_schedules_from_call_multiple_slots() -> None:
    """Test parsing multiple slots from a service call dictionary."""
    data = {
        "slots": [
            {"start_time": "08:00", "end_time": "12:00", "days": ["mon", "tue"]},
            {"start_time": "13:00", "end_time": "17:00", "days": ["mon", "tue"]},
        ]
    }
    schedules = _parse_schedules_from_call(data)
    assert len(schedules) == 4
    # Slot 1: Mon 08-12, Tue 08-12
    assert schedules[0]["start_hour"] == 8 and schedules[0]["week_or_day"] == 1
    assert schedules[1]["start_hour"] == 8 and schedules[1]["week_or_day"] == 2
    # Slot 2: Mon 13-17, Tue 13-17
    assert schedules[2]["start_hour"] == 13 and schedules[2]["week_or_day"] == 1
    assert schedules[3]["start_hour"] == 13 and schedules[3]["week_or_day"] == 2


async def test_async_client_get_passage_mode() -> None:
    """Test async_client_get_passage_mode exchange."""
    client = MagicMock()
    client.key.lockMac = "AA:BB:CC:DD:EE:FF"
    client.key.lockVersion.protocolType = 5
    client.key.lockVersion.protocolVersion = 3
    client.key.lockVersion.scene = 0
    client.key.lockVersion.groupId = 1
    client.key.lockVersion.orgId = 1
    client._aes_key = b"0123456789abcdef"
    client._admin_handshake = AsyncMock()
    client._transport.exchange = AsyncMock()
    client._decrypt_response = MagicMock(return_value=b"decrypted")
    client._parse_response_envelope = MagicMock(
        return_value=(
            CMD_CONFIGURE_PASSAGE_MODE,
            ResponseStatus.SUCCESS,
            bytes([0x50, 0x01, 0x00, 0x01, 0x01, 0x00, 0x09, 0x00, 0x11, 0x00]),
        )
    )

    schedules = await async_client_get_passage_mode(client)
    assert len(schedules) == 1
    assert schedules[0]["start_hour"] == 9
    assert schedules[0]["end_hour"] == 17
    client._admin_handshake.assert_awaited_once()


async def test_async_client_clear_passage_mode() -> None:
    """Test async_client_clear_passage_mode exchange."""
    client = MagicMock()
    client.key.lockMac = "AA:BB:CC:DD:EE:FF"
    client.key.lockVersion.protocolType = 5
    client.key.lockVersion.protocolVersion = 3
    client.key.lockVersion.scene = 0
    client.key.lockVersion.groupId = 1
    client.key.lockVersion.orgId = 1
    client._aes_key = b"0123456789abcdef"
    client._admin_handshake = AsyncMock()
    client._transport.exchange = AsyncMock()
    client._decrypt_response = MagicMock(return_value=b"decrypted")
    client._parse_response_envelope = MagicMock(
        return_value=(CMD_CONFIGURE_PASSAGE_MODE, ResponseStatus.SUCCESS, b"")
    )

    await async_client_clear_passage_mode(client)
    client._admin_handshake.assert_awaited_once()
    client._transport.exchange.assert_awaited_once()


async def test_async_client_set_passage_mode_failure() -> None:
    """Test TTLockError raised on failed response status."""
    client = MagicMock()
    client.key.lockMac = "AA:BB:CC:DD:EE:FF"
    client.key.lockVersion.protocolType = 5
    client.key.lockVersion.protocolVersion = 3
    client.key.lockVersion.scene = 0
    client.key.lockVersion.groupId = 1
    client.key.lockVersion.orgId = 1
    client._aes_key = b"0123456789abcdef"
    client._admin_handshake = AsyncMock()
    client._transport.exchange = AsyncMock()
    client._decrypt_response = MagicMock(return_value=b"decrypted")
    client._parse_response_envelope = MagicMock(
        return_value=(CMD_CONFIGURE_PASSAGE_MODE, ResponseStatus.FAILED, b"\x00")
    )

    schedule: TtlockBlePassageSchedule = {
        "type": PASSAGE_TYPE_WEEKLY,
        "week_or_day": 1,
        "month": 0,
        "start_hour": 8,
        "start_minute": 0,
        "end_hour": 17,
        "end_minute": 0,
    }
    with pytest.raises(TTLockError, match="Failed to set_passage_mode"):
        await async_client_set_passage_mode(client, [schedule])
