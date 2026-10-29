from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.dispatcher import async_dispatcher_send
from pytest_homeassistant_custom_component.common import MockConfigEntry
from ttlock_ble import (
    CardEntry,
    FingerprintEntry,
    KeyboardPwdType,
    LogEntry,
    LogOperate,
    PasscodeEntry,
)

from custom_components.ttlock_ble.connection import log_signal
from custom_components.ttlock_ble.const import DOMAIN
from custom_components.ttlock_ble.credential_store import async_get_credential_store
from custom_components.ttlock_ble.credential_type import TtlockBleCredentialType
from custom_components.ttlock_ble.data import TtlockBleKnownCredential

MAC = "AA:BB:CC:DD:EE:FF"


def _fingerprint(id_byte: int, slot: int) -> FingerprintEntry:
    return FingerprintEntry(
        fingerprint_id=bytes([0x00, 0x00, 0x00, id_byte]),
        slot=slot,
        start_date=None,
        end_date=None,
    )


def _card(number: int) -> CardEntry:
    return CardEntry(card_id=number.to_bytes(4), start_date=None, end_date=None)


def _passcode(code: str) -> PasscodeEntry:
    return PasscodeEntry(
        passcode=code,
        pwd_type=KeyboardPwdType.PERMANENT,
        start_date=None,
        end_date=None,
        cyclic_schedule=None,
    )


async def _read(
    hass, entry, connection, fingerprints=(), cards=(), passcodes=()
) -> None:
    """Have the lock answer these lists to a read the coordinator makes."""
    connection.async_get_fingerprints = AsyncMock(return_value=list(fingerprints))
    connection.async_get_cards = AsyncMock(return_value=list(cards))
    connection.async_get_passcodes = AsyncMock(return_value=list(passcodes))
    assert await entry.runtime_data.coordinator.async_refresh_credentials(MAC)
    await hass.async_block_till_done()


async def _record(hass, record_type, **fields) -> None:
    async_dispatcher_send(
        hass,
        log_signal(MAC),
        LogEntry(
            record_number=1,
            record_type=int(record_type),
            operate_date=dt.datetime(2026, 10, 28, 10, 0),  # noqa: DTZ001 — lock RTC is naive
            lock_battery=80,
            **fields,
        ),
    )
    await hass.async_block_till_done()


def _name_entries(hass, translation_key: str) -> list[er.RegistryEntry]:
    return [
        entry
        for entry in er.async_get(hass).entities.values()
        if entry.platform == DOMAIN and entry.translation_key == translation_key
    ]


def _name_states(hass, translation_key: str) -> dict[str, str]:
    """Every name text of a kind, by its friendly name, with its value."""
    return {
        state.attributes["friendly_name"]: state.state
        for state in (
            hass.states.get(entry.entity_id)
            for entry in _name_entries(hass, translation_key)
        )
        if state is not None
    }


def _count_state(hass, translation_key: str) -> str:
    (entry,) = _name_entries(hass, translation_key)
    return hass.states.get(entry.entity_id).state


async def _set_name(hass, friendly_name: str, value: str) -> None:
    (entity_id,) = (
        state.entity_id
        for state in hass.states.async_all("text")
        if state.attributes["friendly_name"] == friendly_name
    )
    await hass.services.async_call(
        "text", "set_value", {"entity_id": entity_id, "value": value}, blocking=True
    )


async def test_a_key_that_cannot_administer_gets_no_listed_credentials(
    hass,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    key = dict(sample_stored_key)
    key["userType"] = "110302"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "u", "password": "p", "keys": [key]},
        unique_id="u",
    )
    entry.add_to_hass(hass)
    store = await async_get_credential_store(hass)
    store.async_replace(
        MAC,
        TtlockBleCredentialType.CARD,
        [TtlockBleKnownCredential(TtlockBleCredentialType.CARD, "42", "42")],
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert _name_entries(hass, "card_name") == []
    assert _name_entries(hass, "card_count") == []
    assert _name_entries(hass, "fingerprint_count") == []


async def test_a_key_that_cannot_administer_still_learns_passcodes_from_the_log(
    hass,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    key = dict(sample_stored_key)
    key["userType"] = "110302"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "u", "password": "p", "keys": [key]},
        unique_id="u",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await _record(hass, LogOperate.KEYBOARD_PASSWORD_UNLOCK, password="123456")

    assert _name_states(hass, "passcode_name") == {"Front door Passcode 1•••56": ""}


async def test_the_counts_are_unknown_before_any_read(hass, setup_integration) -> None:
    assert _count_state(hass, "fingerprint_count") == "unknown"
    assert _count_state(hass, "card_count") == "unknown"
    assert hass.states.async_all("text") == []


async def test_a_read_creates_one_unnamed_text_per_credential(
    hass, setup_integration, mock_ttlock_connection
) -> None:
    await _read(
        hass,
        setup_integration,
        mock_ttlock_connection,
        fingerprints=[_fingerprint(0x2A, 1), _fingerprint(0x2B, 2)],
        cards=[_card(3819025092)],
        passcodes=[_passcode("123456")],
    )

    assert _count_state(hass, "fingerprint_count") == "2"
    assert _count_state(hass, "card_count") == "1"
    assert _name_states(hass, "fingerprint_name") == {
        "Front door Fingerprint 2752513": "",
        "Front door Fingerprint 2818050": "",
    }
    assert _name_states(hass, "card_name") == {"Front door Card 3819025092": ""}
    assert _name_states(hass, "passcode_name") == {"Front door Passcode 1•••56": ""}


async def test_a_credential_text_is_configuration_on_the_lock_device(
    hass, setup_integration, mock_ttlock_connection
) -> None:
    await _read(
        hass, setup_integration, mock_ttlock_connection, cards=[_card(3819025092)]
    )

    (entry,) = _name_entries(hass, "card_name")
    lock = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, format_mac(MAC)), setup_integration.entry_id
    )
    assert lock is not None
    assert entry.device_id == lock.id
    assert entry.entity_category == er.EntityCategory.CONFIG
    assert entry.unique_id == f"{MAC}_card_3819025092"


async def test_no_passcode_ever_reaches_an_entity(
    hass, setup_integration, mock_ttlock_connection
) -> None:
    await _read(
        hass, setup_integration, mock_ttlock_connection, passcodes=[_passcode("123456")]
    )

    (entry,) = _name_entries(hass, "passcode_name")
    state = hass.states.get(entry.entity_id)
    assert "123456" not in entry.unique_id
    assert "123456" not in entry.entity_id
    assert "123456" not in str(state.as_dict())


async def test_naming_a_credential_stores_the_name(
    hass, setup_integration, mock_ttlock_connection
) -> None:
    await _read(
        hass, setup_integration, mock_ttlock_connection, cards=[_card(3819025092)]
    )

    await _set_name(hass, "Front door Card 3819025092", "Alice")

    assert _name_states(hass, "card_name") == {"Front door Card 3819025092": "Alice"}
    store = await async_get_credential_store(hass)
    assert store.name_of(MAC, TtlockBleCredentialType.CARD, "3819025092") == "Alice"


async def test_the_same_list_read_again_adds_nothing(
    hass, setup_integration, mock_ttlock_connection
) -> None:
    for _ in range(2):
        await _read(
            hass,
            setup_integration,
            mock_ttlock_connection,
            fingerprints=[_fingerprint(0x2A, 1)],
        )

    assert len(_name_entries(hass, "fingerprint_name")) == 1


async def test_a_new_fingerprint_is_added_next_to_the_named_ones(
    hass, setup_integration, mock_ttlock_connection
) -> None:
    await _read(
        hass, setup_integration, mock_ttlock_connection, [_fingerprint(0x2A, 1)]
    )
    await _set_name(hass, "Front door Fingerprint 2752513", "Alice")
    await _read(
        hass,
        setup_integration,
        mock_ttlock_connection,
        [_fingerprint(0x2A, 1), _fingerprint(0x2B, 2)],
    )

    assert _name_states(hass, "fingerprint_name") == {
        "Front door Fingerprint 2752513": "Alice",
        "Front door Fingerprint 2818050": "",
    }


async def test_a_deleted_card_loses_its_text_and_its_name(
    hass, setup_integration, mock_ttlock_connection
) -> None:
    await _read(
        hass,
        setup_integration,
        mock_ttlock_connection,
        cards=[_card(42), _card(7)],
    )
    await _set_name(hass, "Front door Card 42", "Bob")
    await _read(hass, setup_integration, mock_ttlock_connection, cards=[_card(7)])

    assert _count_state(hass, "card_count") == "1"
    assert _name_states(hass, "card_name") == {"Front door Card 7": ""}
    store = await async_get_credential_store(hass)
    assert store.name_of(MAC, TtlockBleCredentialType.CARD, "42") is None


async def test_a_reload_brings_the_credentials_back_with_their_names(
    hass, setup_integration, mock_ttlock_connection
) -> None:
    await _read(
        hass,
        setup_integration,
        mock_ttlock_connection,
        fingerprints=[_fingerprint(0x2A, 1)],
        passcodes=[_passcode("123456")],
    )
    await _set_name(hass, "Front door Fingerprint 2752513", "Alice")
    await _set_name(hass, "Front door Passcode 1•••56", "Bob")
    before = {entry.entity_id for entry in er.async_get(hass).entities.values()}

    await hass.config_entries.async_reload(setup_integration.entry_id)
    await hass.async_block_till_done()

    after = {entry.entity_id for entry in er.async_get(hass).entities.values()}
    assert after == before
    assert _name_states(hass, "fingerprint_name") == {
        "Front door Fingerprint 2752513": "Alice"
    }
    assert _name_states(hass, "passcode_name") == {"Front door Passcode 1•••56": "Bob"}
    assert _count_state(hass, "fingerprint_count") == "1"


async def test_a_fingerprint_deleted_while_unloaded_goes_on_the_first_read(
    hass, setup_integration, mock_ttlock_connection
) -> None:
    await _read(
        hass,
        setup_integration,
        mock_ttlock_connection,
        [_fingerprint(0x2A, 1), _fingerprint(0x2B, 2)],
    )
    await hass.config_entries.async_reload(setup_integration.entry_id)
    await hass.async_block_till_done()

    await _read(
        hass, setup_integration, mock_ttlock_connection, [_fingerprint(0x2B, 2)]
    )

    assert _name_states(hass, "fingerprint_name") == {
        "Front door Fingerprint 2818050": ""
    }


async def test_a_passcode_used_at_the_keypad_is_learned(
    hass, setup_integration
) -> None:
    await _record(hass, LogOperate.KEYBOARD_PASSWORD_UNLOCK, password="123456")
    await _record(hass, LogOperate.ADD_PASSCODE_SUCCESSFULLY, password="987654")

    assert _name_states(hass, "passcode_name") == {
        "Front door Passcode 1•••56": "",
        "Front door Passcode 9•••54": "",
    }


async def test_a_refused_passcode_is_not_learned(hass, setup_integration) -> None:
    await _record(hass, LogOperate.ERROR_PASSWORD_UNLOCK, password="123456")
    await _record(hass, LogOperate.KEYBOARD_PASSWORD_UNLOCK, password=None)

    assert _name_states(hass, "passcode_name") == {}


async def test_a_changed_passcode_keeps_its_name(hass, setup_integration) -> None:
    await _record(hass, LogOperate.KEYBOARD_PASSWORD_UNLOCK, password="123456")
    await _set_name(hass, "Front door Passcode 1•••56", "Alice")

    await _record(
        hass,
        LogOperate.KEYBOARD_MODIFY_PASSWORD,
        password="123456",
        new_password="987654",
    )

    assert _name_states(hass, "passcode_name") == {
        "Front door Passcode 9•••54": "Alice"
    }


async def test_a_change_record_without_the_new_code_changes_nothing(
    hass, setup_integration
) -> None:
    await _record(hass, LogOperate.KEYBOARD_PASSWORD_UNLOCK, password="123456")
    await _record(hass, LogOperate.KEYBOARD_MODIFY_PASSWORD, password="123456")

    assert _name_states(hass, "passcode_name") == {"Front door Passcode 1•••56": ""}


async def test_a_deleted_or_expired_passcode_is_forgotten(
    hass, setup_integration
) -> None:
    await _record(hass, LogOperate.KEYBOARD_PASSWORD_UNLOCK, password="123456")
    await _record(hass, LogOperate.KEYBOARD_PASSWORD_UNLOCK, password="987654")

    await _record(hass, LogOperate.KEYBOARD_REMOVE_SINGLE_PASSWORD, password="123456")
    await _record(hass, LogOperate.PASSCODE_EXPIRED, password="987654")

    assert _name_states(hass, "passcode_name") == {}


async def test_clearing_every_passcode_forgets_them_all(
    hass, setup_integration
) -> None:
    await _record(hass, LogOperate.KEYBOARD_PASSWORD_UNLOCK, password="123456")
    await _record(hass, LogOperate.KEYBOARD_PASSWORD_UNLOCK, password="987654")

    await _record(hass, LogOperate.KEYBOARD_REMOVE_ALL_PASSWORDS)

    assert _name_states(hass, "passcode_name") == {}


async def test_a_record_with_nothing_to_learn_changes_nothing(
    hass, setup_integration
) -> None:
    await _record(hass, LogOperate.FR_UNLOCK_SUCCEED, password="2752513")
    await _record(hass, LogOperate.KEYBOARD_REMOVE_ALL_PASSWORDS)

    assert hass.states.async_all("text") == []
