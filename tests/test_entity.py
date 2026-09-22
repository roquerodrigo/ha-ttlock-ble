from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, format_mac

from custom_components.ttlock_ble.clock_sync_store import TtlockBleClockSyncStore
from custom_components.ttlock_ble.const import DOMAIN, MANUFACTURER
from custom_components.ttlock_ble.coordinator import TtlockBleDataUpdateCoordinator
from custom_components.ttlock_ble.device_description_store import (
    TtlockBleDeviceDescriptionStore,
)
from custom_components.ttlock_ble.entity import (
    TtlockBleEntity,
    TtlockBleFingerprintEntity,
    TtlockBleFingerprintsHubEntity,
)


def _coordinator(hass, description=None, mac=None) -> TtlockBleDataUpdateCoordinator:
    descriptions = TtlockBleDeviceDescriptionStore(hass)
    if description is not None and mac is not None:
        descriptions.async_remember(mac, description)
    return TtlockBleDataUpdateCoordinator(
        hass=hass,
        connections={},
        descriptions=descriptions,
        clock_syncs=TtlockBleClockSyncStore(hass),
    )


def _entity(hass, key, description=None) -> TtlockBleEntity:
    coordinator = _coordinator(hass, description, key.lockMac)
    return TtlockBleEntity(coordinator, key)


async def test_entity_device_info_identifiers_keyed_by_mac(
    hass, sample_virtual_key
) -> None:
    info = _entity(hass, sample_virtual_key).device_info
    mac = format_mac(sample_virtual_key.lockMac)
    assert info["identifiers"] == {(DOMAIN, mac)}
    assert info["connections"] == {(CONNECTION_BLUETOOTH, mac)}


async def test_entity_device_info_name_prefers_alias(hass, sample_virtual_key) -> None:
    info = _entity(hass, sample_virtual_key).device_info
    assert info["name"] == sample_virtual_key.lockAlias


async def test_entity_device_info_manufacturer(hass, sample_virtual_key) -> None:
    info = _entity(hass, sample_virtual_key).device_info
    assert info["manufacturer"] == MANUFACTURER


async def test_entity_device_info_model_carries_protocol(
    hass, sample_virtual_key
) -> None:
    """Until a lock is read, its protocol version is all that is known."""
    info = _entity(hass, sample_virtual_key).device_info
    assert info["model"] == "Protocol 5.3"
    # Spelled out, an unknown version would blank whatever a poll had
    # already stamped on the registry device; left out, it is kept.
    assert "hw_version" not in info
    assert "sw_version" not in info


async def test_entity_device_info_prefers_what_the_lock_reported(
    hass, sample_virtual_key
) -> None:
    info = _entity(
        hass,
        sample_virtual_key,
        description={
            "model": "SN534-4P-T78-BELL",
            "hardware_version": "1.7",
            "firmware_version": "6.5.20.24121101",
        },
    ).device_info
    assert info["model"] == "SN534-4P-T78-BELL"
    assert info["hw_version"] == "1.7"
    assert info["sw_version"] == "6.5.20.24121101"


async def test_entity_device_info_keeps_the_protocol_when_no_model_was_read(
    hass, sample_virtual_key
) -> None:
    """A lock that answers the firmware but not the model keeps both truths."""
    info = _entity(
        hass,
        sample_virtual_key,
        description={
            "model": None,
            "hardware_version": None,
            "firmware_version": "6.5.20.24121101",
        },
    ).device_info
    assert info["model"] == "Protocol 5.3"
    assert "hw_version" not in info
    assert info["sw_version"] == "6.5.20.24121101"


async def test_entity_falls_back_to_lock_name_when_alias_missing(
    hass, sample_virtual_key
) -> None:
    sample_virtual_key.lockAlias = ""
    info = _entity(hass, sample_virtual_key).device_info
    assert info["name"] == sample_virtual_key.lockName


async def test_entity_falls_back_to_mac_when_both_missing(
    hass, sample_virtual_key
) -> None:
    sample_virtual_key.lockAlias = ""
    sample_virtual_key.lockName = ""
    info = _entity(hass, sample_virtual_key).device_info
    assert info["name"] == sample_virtual_key.lockMac


async def test_entity_lock_state_returns_none_when_no_coordinator_data(
    hass, sample_virtual_key
) -> None:
    """Before any successful poll the per-lock state is None."""
    entity = _entity(hass, sample_virtual_key)
    assert entity._lock_state is None


async def test_entity_lock_state_returns_none_when_mac_missing(
    hass, sample_virtual_key
) -> None:
    entity = _entity(hass, sample_virtual_key)
    entity.coordinator.data = {}
    assert entity._lock_state is None


async def test_entity_lock_state_reads_from_coordinator(
    hass, sample_virtual_key
) -> None:
    entity = _entity(hass, sample_virtual_key)
    entity.coordinator.data = {
        sample_virtual_key.lockMac: {
            "locked": True,
            "battery_level": 80,
        },
    }
    assert entity._lock_state is not None
    assert entity._lock_state["locked"] is True


def _hub_entity(hass, key):
    """A `TtlockBleFingerprintsHubEntity` bound to a real registered lock device.

    `via_device_id` resolution needs a real config entry (for
    `coordinator.config_entry`), a real registered lock device (for the
    lookup to resolve), and `entity.hass` - none of which the plain
    `_entity` helper sets up, since the base class's own `device_info`
    never needed them.
    """
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    mac = format_mac(key.lockMac)
    lock_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, mac)},
    )
    coordinator = _coordinator(hass)
    coordinator.config_entry = entry

    entity = TtlockBleFingerprintsHubEntity(coordinator, key)
    entity.hass = hass
    return entity, lock_device


async def test_fingerprints_hub_device_info(hass, sample_virtual_key) -> None:
    entity, lock_device = _hub_entity(hass, sample_virtual_key)
    info = entity.device_info
    mac = format_mac(sample_virtual_key.lockMac)
    assert info["identifiers"] == {(DOMAIN, f"{mac}_fingerprints")}
    assert info["via_device_id"] == lock_device.id
    assert info["name"] == f"{sample_virtual_key.lockAlias} Fingerprints"
    assert info["manufacturer"] == MANUFACTURER


async def test_fingerprints_hub_name_falls_back_to_lock_name(
    hass, sample_virtual_key
) -> None:
    sample_virtual_key.lockAlias = ""
    entity, _lock_device = _hub_entity(hass, sample_virtual_key)
    assert entity.device_info["name"] == f"{sample_virtual_key.lockName} Fingerprints"


async def test_fingerprints_hub_name_falls_back_to_mac(
    hass, sample_virtual_key
) -> None:
    sample_virtual_key.lockAlias = ""
    sample_virtual_key.lockName = ""
    entity, _lock_device = _hub_entity(hass, sample_virtual_key)
    assert entity.device_info["name"] == f"{sample_virtual_key.lockMac} Fingerprints"


def _fingerprint_entity(hass, key, fingerprint_id: bytes, slot: int, *, hub=None):
    """A `TtlockBleFingerprintEntity` bound to a real registered hub device.

    `parent_device_id` resolution needs a real config entry (for
    `coordinator.config_entry`), a real registered "Fingerprints" hub
    device (for the lookup to resolve), and `entity.hass` - none of
    which the plain `_entity` helper sets up, since the base class never
    needed them.
    """
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = _coordinator(hass)
    coordinator.config_entry = entry

    if hub is None:
        mac = format_mac(key.lockMac)
        hub = dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{mac}_fingerprints")},
            name=f"{key.lockAlias or key.lockName or key.lockMac} Fingerprints",
        )

    entity = TtlockBleFingerprintEntity(coordinator, key, fingerprint_id, slot)
    entity.hass = hass
    return entity, hub


async def test_fingerprint_device_info_chains_under_the_hub(
    hass, sample_virtual_key
) -> None:
    entity, hub = _fingerprint_entity(
        hass, sample_virtual_key, bytes([0x00, 0x00, 0x00, 0x2A]), 1
    )
    info = entity.device_info
    mac = format_mac(sample_virtual_key.lockMac)
    assert info["identifiers"] == {(DOMAIN, f"{mac}_fp_0000002a_1")}
    assert info["parent_device_id"] == hub.id


async def test_fingerprint_device_info_name_is_the_bare_number(
    hass, sample_virtual_key
) -> None:
    """Matches the official app: the bare number, never prefixed with the word."""
    fingerprint_id = bytes([0x00, 0x00, 0x00, 0x2A])
    slot = 1
    entity, _hub = _fingerprint_entity(hass, sample_virtual_key, fingerprint_id, slot)
    expected_number = int.from_bytes(fingerprint_id + slot.to_bytes(2, "big"), "big")
    assert entity.device_info["name"] == str(expected_number)


async def test_two_fingerprints_on_the_same_lock_get_distinct_devices(
    hass, sample_virtual_key
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    mac = format_mac(sample_virtual_key.lockMac)
    hub = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{mac}_fingerprints")},
        name=f"{sample_virtual_key.lockAlias} Fingerprints",
    )
    coordinator = _coordinator(hass)
    coordinator.config_entry = entry

    first = TtlockBleFingerprintEntity(
        coordinator, sample_virtual_key, bytes([0x00, 0x00, 0x00, 0x2A]), 1
    )
    first.hass = hass
    second = TtlockBleFingerprintEntity(
        coordinator, sample_virtual_key, bytes([0x00, 0x00, 0x00, 0x2B]), 2
    )
    second.hass = hass

    assert first.device_info["identifiers"] != second.device_info["identifiers"]
    assert first.device_info["parent_device_id"] == hub.id
    assert second.device_info["parent_device_id"] == hub.id
