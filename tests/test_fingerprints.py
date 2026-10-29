from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import format_mac
from pytest_homeassistant_custom_component.common import MockConfigEntry
from ttlock_ble import FingerprintEntry

from custom_components.ttlock_ble.const import DOMAIN
from custom_components.ttlock_ble.data import TtlockBleEnrolledFingerprint
from custom_components.ttlock_ble.fingerprint_store import async_get_fingerprint_store

MAC = "AA:BB:CC:DD:EE:FF"


def _fingerprint(id_byte: int, slot: int) -> FingerprintEntry:
    return FingerprintEntry(
        fingerprint_id=bytes([0x00, 0x00, 0x00, id_byte]),
        slot=slot,
        start_date=None,
        end_date=None,
    )


async def _read(hass, entry, connection, fingerprints) -> None:
    """Have the lock answer `fingerprints` to a read the coordinator makes."""
    connection.async_get_fingerprints = AsyncMock(return_value=fingerprints)
    assert await entry.runtime_data.coordinator.async_refresh_fingerprints(MAC)
    await hass.async_block_till_done()


def _name_entries(hass) -> list[er.RegistryEntry]:
    return [
        entry
        for entry in er.async_get(hass).entities.values()
        if entry.platform == DOMAIN and entry.translation_key == "fingerprint_name"
    ]


def _name_states(hass) -> dict[str, str]:
    """Every fingerprint-name text, by its friendly name, with its value."""
    return {
        state.attributes["friendly_name"]: state.state
        for state in (hass.states.get(entry.entity_id) for entry in _name_entries(hass))
        if state is not None
    }


def _count_state(hass) -> str:
    (entry,) = (
        entry
        for entry in er.async_get(hass).entities.values()
        if entry.platform == DOMAIN and entry.translation_key == "fingerprint_count"
    )
    return hass.states.get(entry.entity_id).state


async def _set_name(hass, friendly_name: str, value: str) -> None:
    (entity_id,) = (
        entry.entity_id
        for entry in _name_entries(hass)
        if hass.states.get(entry.entity_id).attributes["friendly_name"] == friendly_name
    )
    await hass.services.async_call(
        "text", "set_value", {"entity_id": entity_id, "value": value}, blocking=True
    )


async def test_a_key_that_cannot_administer_gets_no_fingerprint_entities(
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
    store = await async_get_fingerprint_store(hass)
    store.async_replace(
        MAC, {TtlockBleEnrolledFingerprint(fingerprint_id=bytes(4), slot=1)}
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert _name_entries(hass) == []
    assert not any(
        entry.translation_key == "fingerprint_count"
        for entry in er.async_get(hass).entities.values()
    )


async def test_the_count_is_unknown_before_any_read(hass, setup_integration) -> None:
    assert _count_state(hass) == "unknown"
    assert _name_states(hass) == {}


async def test_a_read_creates_one_unnamed_text_per_fingerprint(
    hass, setup_integration, mock_ttlock_connection
) -> None:
    await _read(
        hass,
        setup_integration,
        mock_ttlock_connection,
        [_fingerprint(0x2A, 1), _fingerprint(0x2B, 2)],
    )

    assert _count_state(hass) == "2"
    assert _name_states(hass) == {
        "Front door Fingerprint 2752513": "",
        "Front door Fingerprint 2818050": "",
    }


async def test_a_fingerprint_text_is_configuration_on_the_lock_device(
    hass, setup_integration, mock_ttlock_connection
) -> None:
    await _read(
        hass, setup_integration, mock_ttlock_connection, [_fingerprint(0x2A, 1)]
    )

    (entry,) = _name_entries(hass)
    lock = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, format_mac(MAC)), setup_integration.entry_id
    )
    assert lock is not None
    assert entry.device_id == lock.id
    assert entry.entity_category == er.EntityCategory.CONFIG
    assert entry.unique_id == f"{MAC}_fingerprint_0000002a_1"


async def test_naming_a_fingerprint_stores_the_name(
    hass, setup_integration, mock_ttlock_connection
) -> None:
    await _read(
        hass, setup_integration, mock_ttlock_connection, [_fingerprint(0x2A, 1)]
    )

    await _set_name(hass, "Front door Fingerprint 2752513", "Alice")

    assert _name_states(hass) == {"Front door Fingerprint 2752513": "Alice"}
    store = await async_get_fingerprint_store(hass)
    fingerprint = TtlockBleEnrolledFingerprint.from_entry(_fingerprint(0x2A, 1))
    assert store.name_of(MAC, fingerprint) == "Alice"


async def test_the_same_list_read_again_adds_nothing(
    hass, setup_integration, mock_ttlock_connection
) -> None:
    await _read(
        hass, setup_integration, mock_ttlock_connection, [_fingerprint(0x2A, 1)]
    )
    await _read(
        hass, setup_integration, mock_ttlock_connection, [_fingerprint(0x2A, 1)]
    )

    assert len(_name_entries(hass)) == 1


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

    assert _name_states(hass) == {
        "Front door Fingerprint 2752513": "Alice",
        "Front door Fingerprint 2818050": "",
    }


async def test_a_deleted_fingerprint_loses_its_text_and_its_name(
    hass, setup_integration, mock_ttlock_connection
) -> None:
    await _read(
        hass,
        setup_integration,
        mock_ttlock_connection,
        [_fingerprint(0x2A, 1), _fingerprint(0x2B, 2)],
    )
    await _set_name(hass, "Front door Fingerprint 2818050", "Bob")
    await _read(
        hass, setup_integration, mock_ttlock_connection, [_fingerprint(0x2A, 1)]
    )

    assert _count_state(hass) == "1"
    assert _name_states(hass) == {"Front door Fingerprint 2752513": ""}
    store = await async_get_fingerprint_store(hass)
    fingerprint = TtlockBleEnrolledFingerprint.from_entry(_fingerprint(0x2B, 2))
    assert store.name_of(MAC, fingerprint) is None


async def test_a_reload_brings_the_fingerprints_back_with_their_names(
    hass, setup_integration, mock_ttlock_connection
) -> None:
    await _read(
        hass, setup_integration, mock_ttlock_connection, [_fingerprint(0x2A, 1)]
    )
    await _set_name(hass, "Front door Fingerprint 2752513", "Alice")
    (before,) = _name_entries(hass)

    await hass.config_entries.async_reload(setup_integration.entry_id)
    await hass.async_block_till_done()

    (after,) = _name_entries(hass)
    assert after.entity_id == before.entity_id
    assert _name_states(hass) == {"Front door Fingerprint 2752513": "Alice"}
    assert _count_state(hass) == "1"


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

    assert _name_states(hass) == {"Front door Fingerprint 2818050": ""}
