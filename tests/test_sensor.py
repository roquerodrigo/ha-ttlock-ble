from __future__ import annotations

from unittest.mock import AsyncMock


async def test_battery_sensor_created_for_each_key(hass, setup_integration) -> None:
    assert len(hass.states.async_all("sensor")) == 1


async def test_battery_sensor_reports_coordinator_value(
    hass,
    setup_integration,
) -> None:
    state = hass.states.async_all("sensor")[0]
    assert state.state == "80"


async def test_battery_sensor_unit_and_device_class(
    hass,
    setup_integration,
) -> None:
    state = hass.states.async_all("sensor")[0]
    assert state.attributes["unit_of_measurement"] == "%"
    assert state.attributes["device_class"] == "battery"
    assert state.attributes["state_class"] == "measurement"


async def test_battery_sensor_unknown_when_coordinator_returns_none(
    hass,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    mock_ttlock_connection.async_query_state = AsyncMock(return_value=None)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "username": "u",
            "password": "p",
            "keys": [sample_stored_key],
        },
        unique_id="u",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.async_all("sensor")[0]
    assert state.state in ("unknown", "unavailable")


async def test_battery_sensor_has_unique_id(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    from homeassistant.helpers import entity_registry as er

    state = hass.states.async_all("sensor")[0]
    registry = er.async_get(hass)
    entry = registry.async_get(state.entity_id)
    assert entry is not None
    assert entry.unique_id == f"{sample_virtual_key.lockMac}_battery"


async def test_battery_sensor_is_diagnostic(
    hass,
    setup_integration,
) -> None:
    from homeassistant.helpers import entity_registry as er

    state = hass.states.async_all("sensor")[0]
    registry = er.async_get(hass)
    entry = registry.async_get(state.entity_id)
    assert entry is not None
    assert entry.entity_category == er.EntityCategory.DIAGNOSTIC
