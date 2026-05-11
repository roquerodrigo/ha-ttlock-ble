from __future__ import annotations

from datetime import timedelta

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, format_mac

from custom_components.ttlock_ble.const import DOMAIN, MANUFACTURER
from custom_components.ttlock_ble.coordinator import TtlockBleDataUpdateCoordinator
from custom_components.ttlock_ble.entity import TtlockBleEntity


def _entity(hass, key) -> TtlockBleEntity:
    coordinator = TtlockBleDataUpdateCoordinator(
        hass=hass,
        scan_interval=timedelta(seconds=60),
        connections={},
    )
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
    info = _entity(hass, sample_virtual_key).device_info
    assert "protocol" in info["model"]


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
            "available": True,
        },
    }
    assert entity._lock_state is not None
    assert entity._lock_state["locked"] is True
