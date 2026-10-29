"""Coverage for the persisted credentials and their names."""

from __future__ import annotations

from unittest.mock import patch

from custom_components.ttlock_ble.credential_store import (
    STORAGE_KEY,
    STORAGE_VERSION,
    TtlockBleCredentialStore,
)
from custom_components.ttlock_ble.credential_type import TtlockBleCredentialType
from custom_components.ttlock_ble.data import TtlockBleKnownCredential

MAC = "AA:BB:CC:DD:EE:FF"
FINGERPRINT = TtlockBleCredentialType.FINGERPRINT
CARD = TtlockBleCredentialType.CARD
PASSCODE = TtlockBleCredentialType.PASSCODE


def _card(number: str) -> TtlockBleKnownCredential:
    return TtlockBleKnownCredential(CARD, number, number)


def _passcode(code: str) -> TtlockBleKnownCredential:
    return TtlockBleKnownCredential.from_passcode(MAC, code)


async def test_load_tolerates_a_missing_file(hass) -> None:
    store = TtlockBleCredentialStore(hass)
    await store.async_load()
    assert store.known(MAC, CARD) is None


async def test_load_restores_the_credentials_and_their_names(
    hass, hass_storage
) -> None:
    hass_storage[STORAGE_KEY] = {
        "version": STORAGE_VERSION,
        "data": {
            MAC: {
                "card": {
                    "42": {"label": "42", "name": "Alice"},
                    "7": {"label": "7", "name": ""},
                }
            }
        },
    }
    store = TtlockBleCredentialStore(hass)
    await store.async_load()

    assert store.known(MAC, CARD) == [_card("7"), _card("42")]
    assert store.name_of(MAC, CARD, "42") == "Alice"
    assert store.name_of(MAC, CARD, "7") is None


async def test_numbers_come_before_masked_labels(hass) -> None:
    store = TtlockBleCredentialStore(hass)
    store.async_add(MAC, TtlockBleKnownCredential(PASSCODE, "b", "9•••99"))
    store.async_add(MAC, TtlockBleKnownCredential(PASSCODE, "a", "10"))
    store.async_add(MAC, TtlockBleKnownCredential(PASSCODE, "c", "2"))

    assert [c.label for c in store.known(MAC, PASSCODE)] == ["2", "10", "9•••99"]


async def test_a_name_survives_a_new_read_of_the_same_credential(hass) -> None:
    store = TtlockBleCredentialStore(hass)
    store.async_replace(MAC, CARD, [_card("42")])
    store.async_set_name(MAC, CARD, "42", "  Alice ")
    store.async_replace(MAC, CARD, [_card("42"), _card("7")])

    assert store.name_of(MAC, CARD, "42") == "Alice"
    assert store.name_of(MAC, CARD, "7") is None


async def test_a_credential_the_lock_dropped_takes_its_name_with_it(hass) -> None:
    store = TtlockBleCredentialStore(hass)
    store.async_replace(MAC, CARD, [_card("42")])
    store.async_set_name(MAC, CARD, "42", "Alice")
    store.async_replace(MAC, CARD, [])
    store.async_replace(MAC, CARD, [_card("42")])

    assert store.name_of(MAC, CARD, "42") is None


async def test_naming_an_unknown_credential_does_nothing(hass) -> None:
    store = TtlockBleCredentialStore(hass)
    store.async_set_name(MAC, CARD, "42", "Alice")

    assert store.known(MAC, CARD) is None


async def test_an_empty_name_clears_the_one_given(hass) -> None:
    store = TtlockBleCredentialStore(hass)
    store.async_replace(MAC, CARD, [_card("42")])
    store.async_set_name(MAC, CARD, "42", "Alice")
    store.async_set_name(MAC, CARD, "42", "   ")

    assert store.name_of(MAC, CARD, "42") is None


async def test_an_unchanged_list_schedules_no_write(hass) -> None:
    store = TtlockBleCredentialStore(hass)
    store.async_replace(MAC, CARD, [_card("42")])

    with patch.object(store._store, "async_delay_save") as delay_save:
        store.async_replace(MAC, CARD, [_card("42")])

    delay_save.assert_not_called()


async def test_adding_a_known_passcode_again_changes_nothing(hass) -> None:
    store = TtlockBleCredentialStore(hass)

    assert store.async_add(MAC, _passcode("123456")) is True
    assert store.async_add(MAC, _passcode("123456")) is False
    assert len(store.known(MAC, PASSCODE)) == 1


async def test_two_passcodes_showing_the_same_digits_get_distinct_labels(hass) -> None:
    store = TtlockBleCredentialStore(hass)
    store.async_add(MAC, _passcode("123456"))
    store.async_add(MAC, _passcode("199956"))
    store.async_add(MAC, _passcode("100056"))

    assert sorted(c.label for c in store.known(MAC, PASSCODE)) == [
        "1•••56",
        "1•••56 #2",
        "1•••56 #3",
    ]


async def test_a_changed_passcode_keeps_its_name(hass) -> None:
    store = TtlockBleCredentialStore(hass)
    store.async_add(MAC, _passcode("123456"))
    store.async_set_name(MAC, PASSCODE, _passcode("123456").key, "Alice")

    store.async_rekey(MAC, _passcode("123456"), _passcode("987654"))

    assert [c.label for c in store.known(MAC, PASSCODE)] == ["9•••54"]
    assert store.name_of(MAC, PASSCODE, _passcode("987654").key) == "Alice"


async def test_changing_an_unknown_passcode_learns_the_new_one(hass) -> None:
    store = TtlockBleCredentialStore(hass)

    store.async_rekey(MAC, _passcode("123456"), _passcode("987654"))

    assert [c.label for c in store.known(MAC, PASSCODE)] == ["9•••54"]
    assert store.name_of(MAC, PASSCODE, _passcode("987654").key) is None


async def test_removing_and_clearing_report_whether_anything_went(hass) -> None:
    store = TtlockBleCredentialStore(hass)
    store.async_add(MAC, _passcode("123456"))
    store.async_add(MAC, _passcode("987654"))

    assert store.async_remove(MAC, _passcode("123456")) is True
    assert store.async_remove(MAC, _passcode("123456")) is False
    assert store.async_clear(MAC, PASSCODE) is True
    assert store.async_clear(MAC, PASSCODE) is False
    assert store.known(MAC, PASSCODE) == []


async def test_changes_write_the_delayed_snapshot(hass, hass_storage) -> None:
    store = TtlockBleCredentialStore(hass)
    store.async_replace(MAC, CARD, [_card("42")])
    store.async_set_name(MAC, CARD, "42", "Alice")
    await store._store.async_save(store._snapshot())

    assert hass_storage[STORAGE_KEY]["data"] == {
        MAC: {"card": {"42": {"label": "42", "name": "Alice"}}}
    }


async def test_the_store_never_holds_a_passcode_in_clear(hass, hass_storage) -> None:
    store = TtlockBleCredentialStore(hass)
    store.async_add(MAC, _passcode("123456"))
    await store._store.async_save(store._snapshot())

    assert "123456" not in str(hass_storage[STORAGE_KEY]["data"])


async def test_locks_keep_separate_credentials(hass) -> None:
    store = TtlockBleCredentialStore(hass)
    store.async_replace(MAC, CARD, [_card("42")])
    store.async_set_name(MAC, CARD, "42", "Alice")

    assert store.known("11:22:33:44:55:66", CARD) is None
    assert store.name_of("11:22:33:44:55:66", CARD, "42") is None
    assert store.known(MAC, FINGERPRINT) is None


async def test_every_entry_shares_one_store(hass) -> None:
    """Two instances over one storage key take turns dropping each other's writes."""
    from custom_components.ttlock_ble.credential_store import (
        async_get_credential_store,
    )

    first = await async_get_credential_store(hass)
    first.async_replace(MAC, CARD, [_card("42")])
    second = await async_get_credential_store(hass)

    assert second is first
    assert second.known(MAC, CARD) == [_card("42")]


def test_a_passcode_label_shows_its_first_digit_and_last_two_only() -> None:
    assert _passcode("123456").label == "1•••56"
    assert _passcode("1234").label == "1•••34"
    assert _passcode("123").label == "•••"
    assert _passcode("123456").key == _passcode("123456").key
    assert (
        _passcode("123456").key
        != TtlockBleKnownCredential.from_passcode("11:22:33:44:55:66", "123456").key
    )
