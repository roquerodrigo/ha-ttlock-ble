"""Unit tests for Last Unlock Method and Credential Count sensors."""

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock

import pytest
from ttlock_ble import LogEntry
from ttlock_ble.constants import LogOperate

from custom_components.ttlock_ble.sensor import (
    TtlockBleCredentialsCountSensor,
    TtlockBleLastUnlockMethodSensor,
    format_unlock_method,
)


def test_format_unlock_method() -> None:
    """Test formatting various LogEntry types into friendly strings."""
    # Fingerprint
    entry_fp = LogEntry(
        record_number=1,
        record_type=LogOperate.FR_UNLOCK_SUCCEED,
        operate_date=dt.datetime(2026, 9, 2, 10, 0, 0),
        lock_battery=80,
        record_id=1234,
        password="66051",
    )
    assert format_unlock_method(entry_fp) == "Fingerprint (66051)"

    # RFID Card
    entry_card = LogEntry(
        record_number=2,
        record_type=LogOperate.IC_UNLOCK_SUCCEED,
        operate_date=dt.datetime(2026, 9, 2, 10, 5, 0),
        lock_battery=80,
        record_id=1235,
        password="987654321",
    )
    assert format_unlock_method(entry_card) == "RFID Card (987654321)"

    # Passcode (should not expose PIN code)
    entry_pwd = LogEntry(
        record_number=3,
        record_type=LogOperate.KEYBOARD_PASSWORD_UNLOCK,
        operate_date=dt.datetime(2026, 9, 2, 10, 10, 0),
        lock_battery=80,
        record_id=1236,
        password="123456",
    )
    assert format_unlock_method(entry_pwd) == "Passcode"

    # Mobile App
    entry_mobile = LogEntry(
        record_number=4,
        record_type=LogOperate.MOBILE_UNLOCK,
        operate_date=dt.datetime(2026, 9, 2, 10, 15, 0),
        lock_battery=80,
        record_id=1237,
        key_id=42,
    )
    assert format_unlock_method(entry_mobile) == "Mobile App (Key ID: 42)"

    # Auto-Lock
    entry_auto = LogEntry(
        record_number=5,
        record_type=LogOperate.AUTO_LOCK,
        operate_date=dt.datetime(2026, 9, 2, 10, 20, 0),
        lock_battery=80,
        record_id=1238,
    )
    assert format_unlock_method(entry_auto) == "Auto-Lock"

    # Mechanical Key
    entry_mech = LogEntry(
        record_number=6,
        record_type=LogOperate.OPERATE_KEY_UNLOCK,
        operate_date=dt.datetime(2026, 9, 2, 10, 25, 0),
        lock_battery=80,
        record_id=1239,
    )
    assert format_unlock_method(entry_mech) == "Mechanical Key"


@pytest.mark.asyncio
async def test_last_unlock_method_sensor() -> None:
    """Test TtlockBleLastUnlockMethodSensor updates."""
    coordinator = MagicMock()
    key = MagicMock()
    key.lockMac = "AA:BB:CC:DD:EE:FF"
    connection = MagicMock()

    sensor = TtlockBleLastUnlockMethodSensor(coordinator, key, connection)
    assert sensor.unique_id == "AA:BB:CC:DD:EE:FF_last_unlock_method"
    assert sensor.native_value is None

    entry = LogEntry(
        record_number=415,
        record_type=LogOperate.FR_UNLOCK_SUCCEED,
        operate_date=dt.datetime(2026, 9, 2, 9, 43, 48),
        lock_battery=81,
        uid=100,
        record_id=1788338628,
        password="66051",
    )
    sensor._on_log_entry(entry)

    assert sensor.native_value == "Fingerprint (66051)"
    attrs = sensor.extra_state_attributes
    assert attrs["record_number"] == 415
    assert attrs["credential"] == "66051"
    assert attrs["uid"] == 100
    assert attrs["operate_date"] == "2026-09-02T09:43:48"
    assert attrs["record_type"] == "fr_unlock_succeed"


def test_credentials_count_sensor() -> None:
    """Test TtlockBleCredentialsCountSensor."""
    coordinator = MagicMock()
    key = MagicMock()
    key.lockMac = "AA:BB:CC:DD:EE:FF"
    connection = MagicMock()
    connection.get_credential_count.return_value = 5

    sensor = TtlockBleCredentialsCountSensor(coordinator, key, connection, "passcodes")
    assert sensor.unique_id == "AA:BB:CC:DD:EE:FF_passcodes_count"
    assert sensor.native_value == 5

    connection.get_credential_count.return_value = 8
    sensor._on_count_update("cards", 3)
    # Different cred type should not trigger state update for passcodes
    sensor._on_count_update("passcodes", 8)
    assert sensor.native_value == 8
