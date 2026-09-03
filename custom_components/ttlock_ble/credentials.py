"""TTLock V3 BLE protocol queries for passcodes, IC cards, and fingerprints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ttlock_ble import TTLockError
from ttlock_ble.constants import ResponseStatus
from ttlock_ble.protocol import Frame

from .const import LOGGER

if TYPE_CHECKING:
    from ttlock_ble import TTLockClient

CMD_IC_MANAGE = 0x05
CMD_FR_MANAGE = 0x06
CMD_PWD_LIST = 0x07

IC_OP_SEARCH = 1
FR_OP_SEARCH = 1

PASSCODE_TYPE_NAMES: dict[int, str] = {
    1: "permanent",
    2: "period",
    3: "one_time",
    4: "cyclic",
}


def build_passcodes_query_payload(sequence: int = 0) -> bytes:
    """Build payload for querying keyboard passcodes."""
    return bytes([(sequence >> 8) & 0xFF, sequence & 0xFF])


def parse_passcodes_query_response(
    data: bytes,
) -> tuple[int, list[dict[str, Any]]]:
    """Parse payload from a COMM_PWD_LIST response.

    Returns (next_sequence, passcodes).
    """
    if len(data) < 4:
        return 0, []

    next_sequence = int.from_bytes(data[2:4], "big", signed=True)
    passcodes: list[dict[str, Any]] = []
    index = 4

    while index < len(data):
        if index + 3 > len(data):
            break
        # item_len byte
        _item_len = data[index]
        index += 1

        pwd_type = data[index]
        index += 1

        new_pwd_len = data[index]
        index += 1
        if index + new_pwd_len > len(data):
            break
        new_pwd = data[index : index + new_pwd_len].decode("ascii", errors="replace")
        index += new_pwd_len

        if index >= len(data):
            break
        pwd_len = data[index]
        index += 1
        if index + pwd_len > len(data):
            break
        pwd = data[index : index + pwd_len].decode("ascii", errors="replace")
        index += pwd_len

        if index + 5 > len(data):
            break
        start_date = (
            f"20{data[index]:02d}-{data[index + 1]:02d}-{data[index + 2]:02d} "
            f"{data[index + 3]:02d}:{data[index + 4]:02d}"
        )
        index += 5

        end_date: str | None = None
        if pwd_type in (2, 3) and index + 5 <= len(data):
            end_date = (
                f"20{data[index]:02d}-{data[index + 1]:02d}-{data[index + 2]:02d} "
                f"{data[index + 3]:02d}:{data[index + 4]:02d}"
            )
            index += 5
        elif pwd_type == 4 and index + 2 <= len(data):
            index += 2

        passcodes.append({
            "passcode": pwd,
            "new_passcode": new_pwd if new_pwd != pwd else "",
            "type": pwd_type,
            "type_name": PASSCODE_TYPE_NAMES.get(pwd_type, "unknown"),
            "start_date": start_date,
            "end_date": end_date,
        })

    return max(0, next_sequence), passcodes


def build_ic_cards_query_payload(sequence: int = 0) -> bytes:
    """Build payload for querying RFID / IC cards."""
    return bytes([IC_OP_SEARCH, (sequence >> 8) & 0xFF, sequence & 0xFF])


def parse_ic_cards_query_response(
    data: bytes,
) -> tuple[int, list[dict[str, Any]]]:
    """Parse payload from a COMM_IC_MANAGE search response.

    Returns (next_sequence, cards).
    Layout:
      data[0]: battery
      data[1]: opType echo (1)
      data[2:4]: sequence (UInt16BE)
      data[4..]: records of 14 bytes (4 card + 5 start + 5 end)
                 or 18 bytes (8 card + 5 start + 5 end)
    """
    if len(data) < 4:
        return 0, []

    next_sequence = int.from_bytes(data[2:4], "big", signed=True)
    cards: list[dict[str, Any]] = []
    index = 4

    # Determine whether 64-bit (8 bytes) or 32-bit (4 bytes) card IDs
    card_len = 8 if (len(data) - 4) % 18 == 0 and len(data) > 4 else 4
    record_len = card_len + 10

    while index + record_len <= len(data):
        card_num = int.from_bytes(data[index : index + card_len], "big")
        index += card_len

        start_date = (
            f"20{data[index]:02d}-{data[index + 1]:02d}-{data[index + 2]:02d} "
            f"{data[index + 3]:02d}:{data[index + 4]:02d}"
        )
        index += 5

        end_date = (
            f"20{data[index]:02d}-{data[index + 1]:02d}-{data[index + 2]:02d} "
            f"{data[index + 3]:02d}:{data[index + 4]:02d}"
        )
        index += 5

        cards.append({
            "card_number": str(card_num),
            "start_date": start_date,
            "end_date": end_date,
        })

    return max(0, next_sequence), cards


def build_fingerprints_query_payload(sequence: int = 0) -> bytes:
    """Build payload for querying biometric fingerprints."""
    return bytes([FR_OP_SEARCH, (sequence >> 8) & 0xFF, sequence & 0xFF])


def parse_fingerprints_query_response(
    data: bytes,
) -> tuple[int, list[dict[str, Any]]]:
    """Parse payload from a COMM_FR_MANAGE search response.

    Returns (next_sequence, fingerprints).
    Layout:
      data[0]: battery
      data[1]: opType echo (1)
      data[2:4]: sequence (UInt16BE)
      data[4..]: records of 16 bytes (6 fp_id + 5 start + 5 end)
    """
    if len(data) < 4:
        return 0, []

    next_sequence = int.from_bytes(data[2:4], "big", signed=True)
    fingerprints: list[dict[str, Any]] = []
    index = 4
    record_len = 16

    while index + record_len <= len(data):
        fp_num = int.from_bytes(data[index : index + 6], "big")
        index += 6

        start_date = (
            f"20{data[index]:02d}-{data[index + 1]:02d}-{data[index + 2]:02d} "
            f"{data[index + 3]:02d}:{data[index + 4]:02d}"
        )
        index += 5

        end_date = (
            f"20{data[index]:02d}-{data[index + 1]:02d}-{data[index + 2]:02d} "
            f"{data[index + 3]:02d}:{data[index + 4]:02d}"
        )
        index += 5

        fingerprints.append({
            "fingerprint_id": str(fp_num),
            "start_date": start_date,
            "end_date": end_date,
        })

    return max(0, next_sequence), fingerprints


async def async_client_get_passcodes(
    client: TTLockClient,
) -> list[dict[str, Any]]:
    """Query all keyboard passcodes from the lock with pagination."""
    await client._admin_handshake()  # noqa: SLF001
    all_passcodes: list[dict[str, Any]] = []
    sequence = 0
    max_pages = 20

    for _ in range(max_pages):
        payload = build_passcodes_query_payload(sequence)
        frame = Frame.for_lock(
            client.key.lockVersion,
            CMD_PWD_LIST,
            payload,
        ).encrypt_data(client._aes_key)  # noqa: SLF001
        resp = await client._transport.exchange(frame)  # noqa: SLF001
        plain = client._decrypt_response(resp, "get_passcodes")  # noqa: SLF001
        _echo, status, data = client._parse_response_envelope(  # noqa: SLF001
            plain,
            "get_passcodes",
        )
        if status != ResponseStatus.SUCCESS:
            raise TTLockError(
                f"Failed to get_passcodes: lock returned status {status:#x}"
            )
        next_seq, passcodes = parse_passcodes_query_response(data)
        all_passcodes.extend(passcodes)
        if next_seq == 0 or next_seq == sequence or not passcodes:
            break
        sequence = next_seq

    LOGGER.debug(
        "get_passcodes for %s returned %d passcodes in total",
        client.key.lockMac,
        len(all_passcodes),
    )
    return all_passcodes


async def async_client_get_ic_cards(
    client: TTLockClient,
) -> list[dict[str, Any]]:
    """Query all IC cards from the lock with pagination."""
    await client._admin_handshake()  # noqa: SLF001
    all_cards: list[dict[str, Any]] = []
    sequence = 0
    max_pages = 20

    for _ in range(max_pages):
        payload = build_ic_cards_query_payload(sequence)
        frame = Frame.for_lock(
            client.key.lockVersion,
            CMD_IC_MANAGE,
            payload,
        ).encrypt_data(client._aes_key)  # noqa: SLF001
        resp = await client._transport.exchange(frame)  # noqa: SLF001
        plain = client._decrypt_response(resp, "get_cards")  # noqa: SLF001
        _echo, status, data = client._parse_response_envelope(  # noqa: SLF001
            plain,
            "get_cards",
        )
        if status != ResponseStatus.SUCCESS:
            if sequence == 0 and status in (ResponseStatus.FAILED, 0x00, 0x02):
                LOGGER.info(
                    "Lock %s does not support IC cards (status %#x); returning empty list",
                    client.key.lockMac,
                    status,
                )
                return []
            raise TTLockError(
                f"Failed to get_cards: lock returned status {status:#x}"
            )
        next_seq, cards = parse_ic_cards_query_response(data)
        all_cards.extend(cards)
        if next_seq == 0 or next_seq == sequence or not cards:
            break
        sequence = next_seq

    LOGGER.debug(
        "get_cards for %s returned %d cards in total",
        client.key.lockMac,
        len(all_cards),
    )
    return all_cards


async def async_client_get_fingerprints(
    client: TTLockClient,
) -> list[dict[str, Any]]:
    """Query all biometric fingerprints from the lock with pagination."""
    await client._admin_handshake()  # noqa: SLF001
    all_fps: list[dict[str, Any]] = []
    sequence = 0
    max_pages = 20

    for _ in range(max_pages):
        payload = build_fingerprints_query_payload(sequence)
        frame = Frame.for_lock(
            client.key.lockVersion,
            CMD_FR_MANAGE,
            payload,
        ).encrypt_data(client._aes_key)  # noqa: SLF001
        resp = await client._transport.exchange(frame)  # noqa: SLF001
        plain = client._decrypt_response(resp, "get_fingerprints")  # noqa: SLF001
        _echo, status, data = client._parse_response_envelope(  # noqa: SLF001
            plain,
            "get_fingerprints",
        )
        if status != ResponseStatus.SUCCESS:
            if sequence == 0 and status in (ResponseStatus.FAILED, 0x00, 0x02):
                LOGGER.info(
                    "Lock %s does not support fingerprints (status %#x); returning empty list",
                    client.key.lockMac,
                    status,
                )
                return []
            raise TTLockError(
                f"Failed to get_fingerprints: lock returned status {status:#x}"
            )
        next_seq, fps = parse_fingerprints_query_response(data)
        all_fps.extend(fps)
        if next_seq == 0 or next_seq == sequence or not fps:
            break
        sequence = next_seq

    LOGGER.debug(
        "get_fingerprints for %s returned %d fingerprints in total",
        client.key.lockMac,
        len(all_fps),
    )
    return all_fps
