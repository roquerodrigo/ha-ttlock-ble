from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState


async def test_setup_entry_loads_successfully(hass, setup_integration) -> None:
    assert setup_integration.state == ConfigEntryState.LOADED


async def test_setup_entry_registers_update_listener(hass, setup_integration) -> None:
    assert len(setup_integration.update_listeners) == 1


async def test_unload_entry_succeeds(
    hass, setup_integration, mock_ttlock_connection
) -> None:
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    assert setup_integration.state == ConfigEntryState.NOT_LOADED
    mock_ttlock_connection.async_stop.assert_awaited()


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


async def test_setup_starts_each_connection(
    hass, setup_integration, mock_ttlock_connection
) -> None:
    mock_ttlock_connection.async_start.assert_awaited()


async def test_setup_registers_bluetooth_callback_per_lock(
    hass, setup_integration
) -> None:
    assert len(setup_integration.runtime_data.bluetooth_unsubs) == 1


async def test_bluetooth_callback_polls_while_no_state_is_known(
    hass,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    """An advertisement we cannot decode still bootstraps the first reading."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    mock_ttlock_connection.async_query_state = AsyncMock(return_value=None)
    captured_callbacks: list = []

    def _capture(hass_arg, callback, matcher, mode):
        captured_callbacks.append(callback)
        return MagicMock()  # the unsub function

    with patch(
        "custom_components.ttlock_ble.advertisement.async_register_callback",
        side_effect=_capture,
    ):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"username": "u", "password": "p", "keys": [sample_stored_key]},
            unique_id="u",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert len(captured_callbacks) == 1
    service_info = MagicMock()
    service_info.manufacturer_data = {}
    with patch.object(
        entry.runtime_data.coordinator, "async_request_refresh"
    ) as mocked_refresh:
        captured_callbacks[0](service_info, MagicMock())
        await hass.async_block_till_done()
        mocked_refresh.assert_called()


async def test_unload_invokes_bluetooth_unsubs(
    hass,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    from unittest.mock import MagicMock, patch

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    fake_unsub = MagicMock()
    with patch(
        "custom_components.ttlock_ble.advertisement.async_register_callback",
        return_value=fake_unsub,
    ):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"username": "u", "password": "p", "keys": [sample_stored_key]},
            unique_id="u",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
    fake_unsub.assert_called_once()


async def test_setup_creates_lock_and_event_entities(hass, setup_integration) -> None:
    assert len(hass.states.async_all("lock")) == 1
    assert len(hass.states.async_all("event")) == 1


async def test_scan_interval_defaults_to_const(hass, setup_integration) -> None:
    from custom_components.ttlock_ble.const import DEFAULT_SCAN_INTERVAL_SECONDS

    assert setup_integration.runtime_data.coordinator.update_interval == timedelta(
        seconds=DEFAULT_SCAN_INTERVAL_SECONDS,
    )


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


@pytest.mark.parametrize(
    ("options", "expected_cooldown"),
    [
        ({}, 300.0),
        ({"reconnect_interval": 120}, 120.0),
        ({"reconnect_interval": 120, "permanent_connection": True}, 0.0),
    ],
)
async def test_reconnect_options_reach_the_connections(
    hass,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    options,
    expected_cooldown,
) -> None:
    """The configured cooldown is handed to every connection; permanent wins."""
    from unittest.mock import ANY, AsyncMock, MagicMock, patch

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    instance = MagicMock(name="TtlockBleConnection")
    instance.async_start = AsyncMock(return_value=None)
    instance.async_stop = AsyncMock(return_value=None)
    instance.async_query_state = AsyncMock(return_value=(0, 80))
    instance.async_get_operation_log = AsyncMock(return_value=[])
    instance.is_connected = True
    with patch("custom_components.ttlock_ble.TtlockBleConnection") as connection_class:
        connection_class.return_value = instance
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"username": "u", "password": "p", "keys": [sample_stored_key]},
            options=options,
            unique_id="u",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        connection_class.assert_called_once_with(
            hass,
            ANY,
            reconnect_cooldown_seconds=expected_cooldown,
        )


async def test_failed_platform_setup_still_stops_the_connections(
    hass,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    """A platform that cannot be set up must not leave reconnect loops running."""
    from unittest.mock import patch

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "u", "password": "p", "keys": [sample_stored_key]},
        unique_id="u",
    )
    entry.add_to_hass(hass)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        side_effect=ImportError("no such platform"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id) is False
    await hass.async_block_till_done()
    mock_ttlock_connection.async_stop.assert_awaited()
