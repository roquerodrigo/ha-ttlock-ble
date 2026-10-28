from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import format_mac
from pytest_homeassistant_custom_component.common import MockConfigEntry
from ttlock_ble import FingerprintEntry

from custom_components.ttlock_ble.const import DOMAIN

MAC = "AA:BB:CC:DD:EE:FF"
HUB_IDENTIFIER = (DOMAIN, f"{format_mac(MAC)}_fingerprints")


def _fingerprint(id_byte: int, slot: int) -> FingerprintEntry:
    return FingerprintEntry(
        fingerprint_id=bytes([0x00, 0x00, 0x00, id_byte]),
        slot=slot,
        start_date=None,
        end_date=None,
    )


def _fingerprint_identifier(id_byte: int, slot: int) -> tuple[str, str]:
    return (DOMAIN, f"{format_mac(MAC)}_fingerprint_000000{id_byte:02x}_{slot}")


def _read(hass, entry, fingerprints) -> None:
    """Make the coordinator hand out `fingerprints` as a list just read."""
    coordinator = entry.runtime_data.coordinator
    coordinator._fingerprints[MAC] = fingerprints
    coordinator.async_update_listeners()


def _registry_entries(hass, translation_key: str) -> list[er.RegistryEntry]:
    return [
        entry
        for entry in er.async_get(hass).entities.values()
        if entry.platform == DOMAIN and entry.translation_key == translation_key
    ]


def _number_states(hass) -> dict[str, str]:
    """Every fingerprint-number sensor, by unique id, with its live state."""
    return {
        entry.unique_id: hass.states.get(entry.entity_id).state
        for entry in _registry_entries(hass, "fingerprint_number")
    }


def _count_state(hass) -> str:
    entry = _registry_entries(hass, "fingerprint_count")[0]
    return hass.states.get(entry.entity_id).state


def _child_devices(hass, entry) -> list[dr.ChildDeviceEntry]:
    registry = dr.async_get(hass)
    hub = registry.async_get_device_by_identifier(HUB_IDENTIFIER, entry.entry_id)
    assert hub is not None
    return dr.async_entries_for_parent_device(registry, hub.id)


async def _setup_non_admin_entry(hass, sample_stored_key) -> MockConfigEntry:
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
    return entry


async def test_an_admin_key_gets_a_fingerprints_device(hass, setup_integration) -> None:
    registry = dr.async_get(hass)
    lock = registry.async_get_device_by_identifier(
        (DOMAIN, format_mac(MAC)), setup_integration.entry_id
    )
    hub = registry.async_get_device_by_identifier(
        HUB_IDENTIFIER, setup_integration.entry_id
    )

    assert lock is not None
    assert hub is not None
    assert hub.via_device_id == lock.id
    assert hub.name == "Front door Fingerprints"


async def test_a_key_that_cannot_administer_gets_no_fingerprints_device(
    hass,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    entry = await _setup_non_admin_entry(hass, sample_stored_key)

    assert (
        dr.async_get(hass).async_get_device_by_identifier(
            HUB_IDENTIFIER, entry.entry_id
        )
        is None
    )
    assert _registry_entries(hass, "fingerprint_count") == []


async def test_the_count_is_unknown_before_any_read(hass, setup_integration) -> None:
    assert _count_state(hass) == "unknown"
    assert _number_states(hass) == {}


async def test_a_read_creates_one_sensor_per_fingerprint(
    hass, setup_integration
) -> None:
    _read(hass, setup_integration, [_fingerprint(0x2A, 1), _fingerprint(0x2B, 2)])
    await hass.async_block_till_done()

    assert _count_state(hass) == "2"
    assert _number_states(hass) == {
        f"{MAC}_fingerprint_0000002a_1": "2752513",
        f"{MAC}_fingerprint_0000002b_2": "2818050",
    }


async def test_a_fingerprint_sensor_is_diagnostic(hass, setup_integration) -> None:
    _read(hass, setup_integration, [_fingerprint(0x2A, 1)])
    await hass.async_block_till_done()

    entry = _registry_entries(hass, "fingerprint_number")[0]
    assert entry.entity_category == er.EntityCategory.DIAGNOSTIC


async def test_each_fingerprint_is_a_child_of_the_fingerprints_device(
    hass, setup_integration
) -> None:
    _read(hass, setup_integration, [_fingerprint(0x2A, 1)])
    await hass.async_block_till_done()

    (child,) = _child_devices(hass, setup_integration)
    assert child.identifiers == {_fingerprint_identifier(0x2A, 1)}
    assert child.name == "2752513"
    entry = _registry_entries(hass, "fingerprint_number")[0]
    assert entry.device_id == child.id


async def test_the_same_list_read_again_adds_nothing(hass, setup_integration) -> None:
    _read(hass, setup_integration, [_fingerprint(0x2A, 1)])
    await hass.async_block_till_done()
    _read(hass, setup_integration, [_fingerprint(0x2A, 1)])
    await hass.async_block_till_done()

    assert len(_number_states(hass)) == 1
    assert len(_child_devices(hass, setup_integration)) == 1


async def test_a_new_fingerprint_is_added_next_to_the_known_ones(
    hass, setup_integration
) -> None:
    _read(hass, setup_integration, [_fingerprint(0x2A, 1)])
    await hass.async_block_till_done()
    _read(hass, setup_integration, [_fingerprint(0x2A, 1), _fingerprint(0x2B, 2)])
    await hass.async_block_till_done()

    assert set(_number_states(hass).values()) == {"2752513", "2818050"}


async def test_a_deleted_fingerprint_loses_its_device_and_sensor(
    hass, setup_integration
) -> None:
    _read(hass, setup_integration, [_fingerprint(0x2A, 1), _fingerprint(0x2B, 2)])
    await hass.async_block_till_done()
    _read(hass, setup_integration, [_fingerprint(0x2A, 1)])
    await hass.async_block_till_done()

    assert _count_state(hass) == "1"
    assert _number_states(hass) == {f"{MAC}_fingerprint_0000002a_1": "2752513"}
    assert [child.name for child in _child_devices(hass, setup_integration)] == [
        "2752513"
    ]


async def test_a_reload_keeps_the_fingerprint_devices_and_their_names(
    hass, setup_integration
) -> None:
    _read(hass, setup_integration, [_fingerprint(0x2A, 1)])
    await hass.async_block_till_done()
    registry = dr.async_get(hass)
    (child,) = _child_devices(hass, setup_integration)
    registry.async_update_child_device(child.id, name_by_user="Thumb")

    await hass.config_entries.async_reload(setup_integration.entry_id)
    await hass.async_block_till_done()

    (restored,) = _child_devices(hass, setup_integration)
    assert restored.id == child.id
    assert restored.name_by_user == "Thumb"
    assert _number_states(hass) == {f"{MAC}_fingerprint_0000002a_1": "2752513"}


async def test_a_fingerprint_deleted_while_unloaded_goes_on_the_first_read(
    hass, setup_integration
) -> None:
    _read(hass, setup_integration, [_fingerprint(0x2A, 1), _fingerprint(0x2B, 2)])
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(setup_integration.entry_id)
    await hass.async_block_till_done()

    _read(hass, setup_integration, [_fingerprint(0x2B, 2)])
    await hass.async_block_till_done()

    assert _number_states(hass) == {f"{MAC}_fingerprint_0000002b_2": "2818050"}


async def test_a_child_device_that_is_no_fingerprint_is_left_alone(
    hass, setup_integration
) -> None:
    registry = dr.async_get(hass)
    hub = registry.async_get_device_by_identifier(
        HUB_IDENTIFIER, setup_integration.entry_id
    )
    assert hub is not None
    registry.async_get_or_create_child(
        config_entry_id=setup_integration.entry_id,
        parent_device_id=hub.id,
        identifiers={(DOMAIN, f"{format_mac(MAC)}_fingerprint_not-hex_1")},
    )
    registry.async_get_or_create_child(
        config_entry_id=setup_integration.entry_id,
        parent_device_id=hub.id,
        identifiers={(DOMAIN, "something_else")},
    )

    await hass.config_entries.async_reload(setup_integration.entry_id)
    await hass.async_block_till_done()

    assert _number_states(hass) == {}
    assert len(_child_devices(hass, setup_integration)) == 2
