from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState


async def test_setup_entry_loads_successfully(hass, setup_integration) -> None:
    assert setup_integration.state == ConfigEntryState.LOADED


async def test_setup_entry_registers_update_listener(hass, setup_integration) -> None:
    assert len(setup_integration.update_listeners) == 1


async def test_unload_entry_succeeds(hass, setup_integration) -> None:
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    assert setup_integration.state == ConfigEntryState.NOT_LOADED


async def test_reload_entry_restores_loaded_state(hass, setup_integration) -> None:
    await hass.config_entries.async_reload(setup_integration.entry_id)
    await hass.async_block_till_done()
    assert setup_integration.state == ConfigEntryState.LOADED


async def test_async_reload_entry_calls_reload(hass, setup_integration) -> None:
    from custom_components.ttlock_ble import async_reload_entry

    await async_reload_entry(hass, setup_integration)
    await hass.async_block_till_done()
    assert setup_integration.state == ConfigEntryState.LOADED


async def test_runtime_data_populated(
    hass,
    setup_integration,
    sample_stored_key,
    sample_virtual_key,
) -> None:
    rd = setup_integration.runtime_data
    assert rd.coordinator is not None
    assert rd.keys == [sample_stored_key]
    assert len(rd.virtual_keys) == 1
    assert rd.virtual_keys[0].lockMac == sample_virtual_key.lockMac
    assert sample_virtual_key.lockMac in rd.connections


async def test_setup_creates_lock_and_binary_sensor(hass, setup_integration) -> None:
    assert len(hass.states.async_all("lock")) == 1
    assert len(hass.states.async_all("binary_sensor")) == 1


async def test_scan_interval_defaults_to_const(hass, setup_integration) -> None:
    from custom_components.ttlock_ble.const import DEFAULT_SCAN_INTERVAL_SECONDS

    assert setup_integration.runtime_data.coordinator.update_interval == timedelta(
        seconds=DEFAULT_SCAN_INTERVAL_SECONDS,
    )


async def test_default_scan_interval_is_one_hour() -> None:
    """The on-demand model relies on a one-hour default polling cadence."""
    from custom_components.ttlock_ble.const import DEFAULT_SCAN_INTERVAL_SECONDS

    assert DEFAULT_SCAN_INTERVAL_SECONDS == 3600


async def test_scan_interval_picks_up_options(
    hass,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    from homeassistant.const import CONF_SCAN_INTERVAL
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "u", "password": "p", "keys": [sample_stored_key]},
        options={CONF_SCAN_INTERVAL: 120},
        unique_id="u",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.coordinator.update_interval == timedelta(seconds=120)
