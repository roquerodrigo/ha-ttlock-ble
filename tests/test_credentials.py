"""Unit tests for TTLock BLE credentials queries (passcodes, cards, fingerprints)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ttlock_ble.credentials import (
    CMD_FR_MANAGE,
    CMD_IC_MANAGE,
    CMD_PWD_LIST,
    async_client_get_fingerprints,
    async_client_get_ic_cards,
    async_client_get_passcodes,
    build_fingerprints_query_payload,
    build_ic_cards_query_payload,
    build_passcodes_query_payload,
    parse_fingerprints_query_response,
    parse_ic_cards_query_response,
    parse_passcodes_query_response,
)
from ttlock_ble.constants import ResponseStatus


def test_build_payloads() -> None:
    """Test payload builders for credentials."""
    assert build_passcodes_query_payload(0) == bytes([0x00, 0x00])
    assert build_passcodes_query_payload(1) == bytes([0x00, 0x01])

    assert build_ic_cards_query_payload(0) == bytes([0x01, 0x00, 0x00])
    assert build_ic_cards_query_payload(2) == bytes([0x01, 0x00, 0x02])

    assert build_fingerprints_query_payload(0) == bytes([0x01, 0x00, 0x00])
    assert build_fingerprints_query_payload(5) == bytes([0x01, 0x00, 0x05])


def test_parse_passcodes_query_response() -> None:
    """Test parsing keyboard passcodes response."""
    assert parse_passcodes_query_response(b"") == (0, [])
    assert parse_passcodes_query_response(bytes([0x00, 0x00])) == (0, [])

    # Format:
    # data[0:2]: totalLen
    # data[2:4]: sequence (0=done)
    # entry 1: item_len, type=1 (permanent), new_pwd_len=4 ("1234"), pwd_len=4 ("1234"), start_date (5 bytes: 26, 9, 2, 8, 0)
    data = bytes([
        0x00,
        0x01,  # totalLen
        0x00,
        0x00,  # sequence=0
        # Entry:
        16,  # item_len
        0x01,  # type=1 permanent
        0x04,  # new_pwd_len
        0x31,
        0x32,
        0x33,
        0x34,  # "1234"
        0x04,  # pwd_len
        0x31,
        0x32,
        0x33,
        0x34,  # "1234"
        26,
        9,
        2,
        8,
        0,  # 2026-09-02 08:00
    ])
    next_seq, passcodes = parse_passcodes_query_response(data)
    assert next_seq == 0
    assert len(passcodes) == 1
    assert passcodes[0]["passcode"] == "1234"
    assert passcodes[0]["type"] == 1
    assert passcodes[0]["type_name"] == "permanent"
    assert passcodes[0]["start_date"] == "2026-09-02 08:00"
    assert passcodes[0]["end_date"] is None


def test_parse_ic_cards_query_response() -> None:
    """Test parsing IC cards response."""
    assert parse_ic_cards_query_response(b"") == (0, [])

    # data[0]: battery=80
    # data[1]: opType=1
    # data[2:4]: sequence=0
    # record: 4 bytes card ID (12345678), 5 bytes start, 5 bytes end
    data = bytes([
        0x50,  # battery=80
        0x01,  # opType=1
        0x00,
        0x00,  # sequence=0
        0x00,
        0xBC,
        0x61,
        0x4E,  # card number = 12345678
        26,
        9,
        2,
        8,
        0,  # start: 2026-09-02 08:00
        26,
        9,
        2,
        18,
        0,  # end: 2026-09-02 18:00
    ])
    next_seq, cards = parse_ic_cards_query_response(data)
    assert next_seq == 0
    assert len(cards) == 1
    assert cards[0]["card_number"] == "12345678"
    assert cards[0]["start_date"] == "2026-09-02 08:00"
    assert cards[0]["end_date"] == "2026-09-02 18:00"


def test_parse_fingerprints_query_response() -> None:
    """Test parsing fingerprints response."""
    assert parse_fingerprints_query_response(b"") == (0, [])

    # data[0]: battery=80
    # data[1]: opType=1
    # data[2:4]: sequence=0
    # record: 6 bytes fp ID, 5 bytes start, 5 bytes end
    data = bytes([
        0x50,  # battery=80
        0x01,  # opType=1
        0x00,
        0x00,  # sequence=0
        0x00,
        0x00,
        0x00,
        0x01,
        0x02,
        0x03,  # fp ID = 66051
        26,
        9,
        2,
        8,
        0,  # start: 2026-09-02 08:00
        26,
        9,
        2,
        18,
        0,  # end: 2026-09-02 18:00
    ])
    next_seq, fps = parse_fingerprints_query_response(data)
    assert next_seq == 0
    assert len(fps) == 1
    assert fps[0]["fingerprint_id"] == "66051"
    assert fps[0]["start_date"] == "2026-09-02 08:00"
    assert fps[0]["end_date"] == "2026-09-02 18:00"


@pytest.mark.asyncio
async def test_async_client_get_passcodes() -> None:
    """Test client passcodes query exchange."""
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
            CMD_PWD_LIST,
            ResponseStatus.SUCCESS,
            bytes([0x00, 0x00, 0x00, 0x00]),
        )
    )

    passcodes = await async_client_get_passcodes(client)
    assert passcodes == []
    client._admin_handshake.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_client_get_ic_cards() -> None:
    """Test client IC cards query exchange."""
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
            CMD_IC_MANAGE,
            ResponseStatus.SUCCESS,
            bytes([0x50, 0x01, 0x00, 0x00]),
        )
    )

    cards = await async_client_get_ic_cards(client)
    assert cards == []
    client._admin_handshake.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_client_get_fingerprints() -> None:
    """Test client fingerprints query exchange."""
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
            CMD_FR_MANAGE,
            ResponseStatus.SUCCESS,
            bytes([0x50, 0x01, 0x00, 0x00]),
        )
    )

    fps = await async_client_get_fingerprints(client)
    assert fps == []
    client._admin_handshake.assert_awaited_once()
