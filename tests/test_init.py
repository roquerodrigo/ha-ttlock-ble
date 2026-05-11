from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState


async def test_setup_entry_loads_successfully(hass, setup_integration):
    assert setup_integration.state == ConfigEntryState.LOADED


async def test_setup_entry_creates_sensor_entity(hass, setup_integration):
    assert len(hass.states.async_all("sensor")) == 1


async def test_setup_entry_sensor_state(hass, setup_integration):
    state = next(iter(hass.states.async_all("sensor")))
    assert state.state == "sunt aut facere repellat provident"


async def test_setup_entry_registers_update_listener(hass, setup_integration):
    assert len(setup_integration.update_listeners) == 1


async def test_unload_entry_succeeds(hass, setup_integration):
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    assert setup_integration.state == ConfigEntryState.NOT_LOADED


async def test_unload_entry_makes_entities_unavailable(hass, setup_integration):
    await hass.config_entries.async_unload(setup_integration.entry_id)
    await hass.async_block_till_done()
    for state in hass.states.async_all("sensor"):
        assert state.state == "unavailable"


async def test_reload_entry_restores_loaded_state(
    hass, setup_integration, mock_api_client
):
    await hass.config_entries.async_reload(setup_integration.entry_id)
    await hass.async_block_till_done()
    assert setup_integration.state == ConfigEntryState.LOADED


async def test_async_reload_entry_calls_reload(
    hass, setup_integration, mock_api_client
):
    from custom_components.integration_blueprint import async_reload_entry

    await async_reload_entry(hass, setup_integration)
    await hass.async_block_till_done()
    assert setup_integration.state == ConfigEntryState.LOADED


async def test_runtime_data_populated(hass, setup_integration):
    assert setup_integration.runtime_data.client is not None
    assert setup_integration.runtime_data.coordinator is not None
    assert setup_integration.runtime_data.integration is not None


async def test_scan_interval_defaults_to_const(hass, setup_integration):
    from datetime import timedelta

    from custom_components.integration_blueprint.const import (
        DEFAULT_SCAN_INTERVAL_SECONDS,
    )

    assert setup_integration.runtime_data.coordinator.update_interval == timedelta(
        seconds=DEFAULT_SCAN_INTERVAL_SECONDS
    )


async def test_scan_interval_picks_up_options(
    hass, mock_api_client, enable_custom_integrations
):
    from homeassistant.const import CONF_SCAN_INTERVAL
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.integration_blueprint.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "user", "password": "pass"},
        options={CONF_SCAN_INTERVAL: 60},
        unique_id="user",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    from datetime import timedelta

    assert entry.runtime_data.coordinator.update_interval == timedelta(seconds=60)
