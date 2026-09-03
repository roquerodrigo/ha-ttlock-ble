"""TTLock V3 BLE passage mode protocol commands and helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ttlock_ble import TTLockError
from ttlock_ble.constants import ResponseStatus
from ttlock_ble.protocol import Frame

from .const import LOGGER

if TYPE_CHECKING:
    from ttlock_ble import TTLockClient

    from .data import TtlockBlePassageSchedule

CMD_CONFIGURE_PASSAGE_MODE = 0x66

PASSAGE_MODE_QUERY = 1
PASSAGE_MODE_ADD = 2
PASSAGE_MODE_DELETE = 3
PASSAGE_MODE_CLEAR = 4

PASSAGE_TYPE_WEEKLY = 1
PASSAGE_TYPE_MONTHLY = 2


def build_passage_query_payload(sequence: int = 0) -> bytes:
    """Build payload for querying configured passage mode slots."""
    return bytes([PASSAGE_MODE_QUERY, sequence & 0xFF])


def build_passage_clear_payload() -> bytes:
    """Build payload for clearing all passage mode slots."""
    return bytes([PASSAGE_MODE_CLEAR])


def build_passage_set_payload(schedule: TtlockBlePassageSchedule) -> bytes:
    """Build payload for adding or updating a passage mode slot."""
    start_hour = schedule["start_hour"]
    start_minute = schedule["start_minute"]
    end_hour = schedule["end_hour"]
    end_minute = schedule["end_minute"]
    week_or_day = schedule["week_or_day"]
    recurrence_type = schedule.get("type", PASSAGE_TYPE_WEEKLY)
    month = schedule.get("month", 0)

    if not (0 <= start_hour <= 23 and 0 <= start_minute <= 59):
        raise ValueError(f"Invalid start time: {start_hour:02d}:{start_minute:02d}")
    if not (0 <= end_hour <= 23 and 0 <= end_minute <= 59):
        raise ValueError(f"Invalid end time: {end_hour:02d}:{end_minute:02d}")
    if not (0 <= week_or_day <= 7):
        raise ValueError(f"Invalid week_or_day: {week_or_day}")

    return bytes([
        PASSAGE_MODE_ADD,
        recurrence_type & 0xFF,
        week_or_day & 0xFF,
        month & 0xFF,
        start_hour & 0xFF,
        start_minute & 0xFF,
        end_hour & 0xFF,
        end_minute & 0xFF,
    ])


def build_passage_delete_payload(schedule: TtlockBlePassageSchedule) -> bytes:
    """Build payload for deleting a specific passage mode slot."""
    start_hour = schedule["start_hour"]
    start_minute = schedule["start_minute"]
    end_hour = schedule["end_hour"]
    end_minute = schedule["end_minute"]
    week_or_day = schedule["week_or_day"]
    recurrence_type = schedule.get("type", PASSAGE_TYPE_WEEKLY)
    month = schedule.get("month", 0)

    return bytes([
        PASSAGE_MODE_DELETE,
        recurrence_type & 0xFF,
        week_or_day & 0xFF,
        month & 0xFF,
        start_hour & 0xFF,
        start_minute & 0xFF,
        end_hour & 0xFF,
        end_minute & 0xFF,
    ])


def parse_passage_query_response(
    data: bytes,
) -> tuple[int, list[TtlockBlePassageSchedule]]:
    """Parse raw payload from a query passage mode response into schedule slots.

    Payload layout (after the response envelope):
      data[0]: battery percentage
      data[1]: opType echo (1 = QUERY)
      data[2]: sequence number for next page (0 = finished / no more records)
      data[3..]: 7 bytes per schedule:
        type (1 byte)
        week_or_day (1 byte)
        month (1 byte)
        start_hour (1 byte)
        start_minute (1 byte)
        end_hour (1 byte)
        end_minute (1 byte)
    """
    if len(data) < 3:
        return 0, []

    next_sequence = data[2]
    schedules: list[TtlockBlePassageSchedule] = []
    offset = 3
    while offset + 7 <= len(data):
        item: TtlockBlePassageSchedule = {
            "type": data[offset],
            "week_or_day": data[offset + 1],
            "month": data[offset + 2],
            "start_hour": data[offset + 3],
            "start_minute": data[offset + 4],
            "end_hour": data[offset + 5],
            "end_minute": data[offset + 6],
        }
        schedules.append(item)
        offset += 7
    return next_sequence, schedules


async def async_client_get_passage_mode(
    client: TTLockClient,
) -> list[TtlockBlePassageSchedule]:
    """Query all passage mode schedule slots from the lock with pagination."""
    await client._admin_handshake()  # noqa: SLF001
    all_schedules: list[TtlockBlePassageSchedule] = []
    sequence = 0
    max_pages = 10  # safety limit against infinite pagination loops

    for _ in range(max_pages):
        payload = build_passage_query_payload(sequence)
        frame = Frame.for_lock(
            client.key.lockVersion,
            CMD_CONFIGURE_PASSAGE_MODE,
            payload,
        ).encrypt_data(client._aes_key)  # noqa: SLF001
        resp = await client._transport.exchange(frame)  # noqa: SLF001
        plain = client._decrypt_response(resp, "get_passage_mode")  # noqa: SLF001
        _echo, status, data = client._parse_response_envelope(  # noqa: SLF001
            plain,
            "get_passage_mode",
        )
        if status != ResponseStatus.SUCCESS:
            raise TTLockError(
                f"Failed to get_passage_mode: lock returned failure status {status:#x}"
            )
        LOGGER.debug(
            "get_passage_mode response for %s: plain=%s",
            client.key.lockMac,
            plain.hex(),
        )
        next_seq, schedules = parse_passage_query_response(data)
        all_schedules.extend(schedules)
        if next_seq == 0 or next_seq == sequence or not schedules:
            break
        sequence = next_seq

    LOGGER.debug(
        "get_passage_mode for %s returned %d schedule slots in total",
        client.key.lockMac,
        len(all_schedules),
    )
    return all_schedules


async def async_client_clear_passage_mode(client: TTLockClient) -> None:
    """Clear all passage mode schedule slots from the lock."""
    await client._admin_handshake()  # noqa: SLF001
    payload = build_passage_clear_payload()
    frame = Frame.for_lock(
        client.key.lockVersion,
        CMD_CONFIGURE_PASSAGE_MODE,
        payload,
    ).encrypt_data(client._aes_key)  # noqa: SLF001
    resp = await client._transport.exchange(frame)  # noqa: SLF001
    plain = client._decrypt_response(resp, "clear_passage_mode")  # noqa: SLF001
    _echo, status, _data = client._parse_response_envelope(  # noqa: SLF001
        plain,
        "clear_passage_mode",
    )
    if status != ResponseStatus.SUCCESS:
        raise TTLockError(
            f"Failed to clear_passage_mode: lock returned failure status {status:#x}"
        )
    LOGGER.debug("clear_passage_mode succeeded for %s", client.key.lockMac)


async def async_client_delete_passage_mode(
    client: TTLockClient,
    schedule: TtlockBlePassageSchedule,
) -> None:
    """Delete a specific passage mode slot from the lock."""
    await client._admin_handshake()  # noqa: SLF001
    payload = build_passage_delete_payload(schedule)
    frame = Frame.for_lock(
        client.key.lockVersion,
        CMD_CONFIGURE_PASSAGE_MODE,
        payload,
    ).encrypt_data(client._aes_key)  # noqa: SLF001
    resp = await client._transport.exchange(frame)  # noqa: SLF001
    plain = client._decrypt_response(resp, "delete_passage_mode")  # noqa: SLF001
    _echo, status, _data = client._parse_response_envelope(  # noqa: SLF001
        plain,
        "delete_passage_mode",
    )
    if status != ResponseStatus.SUCCESS:
        raise TTLockError(
            f"Failed to delete_passage_mode: lock returned failure status {status:#x}"
        )
    LOGGER.debug("delete_passage_mode succeeded for %s", client.key.lockMac)


async def async_client_set_passage_mode(
    client: TTLockClient,
    schedules: list[TtlockBlePassageSchedule],
    *,
    clear_existing: bool = False,
) -> None:
    """Set one or more passage mode schedule slots on the lock."""
    if clear_existing:
        await async_client_clear_passage_mode(client)

    for schedule in schedules:
        await client._admin_handshake()  # noqa: SLF001
        payload = build_passage_set_payload(schedule)
        frame = Frame.for_lock(
            client.key.lockVersion,
            CMD_CONFIGURE_PASSAGE_MODE,
            payload,
        ).encrypt_data(client._aes_key)  # noqa: SLF001
        resp = await client._transport.exchange(frame)  # noqa: SLF001
        plain = client._decrypt_response(resp, "set_passage_mode")  # noqa: SLF001
        _echo, status, _data = client._parse_response_envelope(  # noqa: SLF001
            plain,
            "set_passage_mode",
        )
        if status != ResponseStatus.SUCCESS:
            raise TTLockError(
                f"Failed to set_passage_mode: lock returned failure status {status:#x}"
            )
    LOGGER.debug(
        "set_passage_mode succeeded for %s (%d slots)",
        client.key.lockMac,
        len(schedules),
    )
