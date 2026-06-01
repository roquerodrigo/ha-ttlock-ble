from __future__ import annotations

import datetime as dt

import pytest
from homeassistant.helpers.dispatcher import async_dispatcher_send
from ttlock_ble import LogEntry, LogOperate

from custom_components.ttlock_ble.connection import log_signal
from custom_components.ttlock_ble.event import _classify_record, _record_type_name


def _log_state(hass):
    """Return the log event entity state."""
    return next(s for s in hass.states.async_all("event") if "log" in s.entity_id)


@pytest.mark.parametrize(
    ("record_type", "expected"),
    [
        (LogOperate.MOBILE_UNLOCK, "unlock"),
        (LogOperate.OPERATE_BLE_LOCK, "lock"),
        (LogOperate.ERROR_PASSWORD_UNLOCK, "unlock_failed"),
        (LogOperate.KEYBOARD_MODIFY_PASSWORD, "password_change"),
        (9999, "other"),
    ],
)
def test_classify_record_covers_every_bucket(record_type, expected) -> None:
    assert _classify_record(record_type) == expected


def test_record_type_name_known_value() -> None:
    assert _record_type_name(LogOperate.MOBILE_UNLOCK) == "mobile_unlock"


def test_record_type_name_unknown_value_falls_back_to_str() -> None:
    assert _record_type_name(9999) == "9999"


async def test_event_entity_created_for_each_key(hass, setup_integration) -> None:
    states = hass.states.async_all("event")
    assert len(states) == 1


async def test_log_event_fires_on_new_record(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    """Log entity fires when a LogEntry arrives via the log dispatcher signal."""
    entry = LogEntry(
        record_number=1,
        record_type=4,
        operate_date=dt.datetime(2026, 5, 17, 10, 0, 0),  # noqa: DTZ001 — lock RTC is naive
        lock_battery=85,
        uid=1234,
        password="123456",
    )
    async_dispatcher_send(
        hass,
        log_signal(sample_virtual_key.lockMac),
        entry,
    )
    await hass.async_block_till_done()
    state = _log_state(hass)
    assert state.attributes["event_type"] == "unlock"
    assert state.attributes["record_type"] == "keyboard_password_unlock"
    assert state.attributes["timestamp"] == "2026-05-17T10:00:00"
    assert state.attributes["battery"] == 85
    assert state.attributes["uid"] == 1234
    assert state.attributes["credential"] == "123456"


async def test_log_event_includes_key_id_and_accessory_battery(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    """Optional `key_id` / `accessory_battery` fields land in event attributes."""
    entry = LogEntry(
        record_number=2,
        record_type=int(LogOperate.OPERATE_BLE_LOCK),
        operate_date=None,
        lock_battery=70,
        key_id=99,
        accessory_battery=55,
    )
    async_dispatcher_send(
        hass,
        log_signal(sample_virtual_key.lockMac),
        entry,
    )
    await hass.async_block_till_done()
    state = _log_state(hass)
    assert state.attributes["event_type"] == "lock"
    assert state.attributes["key_id"] == 99
    assert state.attributes["accessory_battery"] == 55
    assert "timestamp" not in state.attributes


async def test_log_event_has_unique_id(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    from homeassistant.helpers import entity_registry as er

    state = _log_state(hass)
    registry = er.async_get(hass)
    reg_entry = registry.async_get(state.entity_id)
    assert reg_entry is not None
    assert reg_entry.unique_id == f"{sample_virtual_key.lockMac}_log"
