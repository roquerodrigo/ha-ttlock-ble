from __future__ import annotations

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ttlock_ble.const import (
    CONF_PERMANENT_CONNECTION,
    CONF_RECONNECT_INTERVAL,
    DEFAULT_RECONNECT_INTERVAL_SECONDS,
    DEFAULT_SCAN_INTERVAL_SECONDS,
)


def _schema_default(result, key):
    schema = result["data_schema"].schema
    schema_key = next(k for k in schema if getattr(k, "schema", k) == key)
    return schema_key.default()


async def test_options_flow_shows_form_with_defaults(hass, setup_integration):
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert _schema_default(result, CONF_SCAN_INTERVAL) == DEFAULT_SCAN_INTERVAL_SECONDS
    assert (
        _schema_default(result, CONF_RECONNECT_INTERVAL)
        == DEFAULT_RECONNECT_INTERVAL_SECONDS
    )
    assert _schema_default(result, CONF_PERMANENT_CONNECTION) is False


async def test_options_flow_persists_all_options(hass, setup_integration):
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_SCAN_INTERVAL: 60,
            CONF_RECONNECT_INTERVAL: 120,
            CONF_PERMANENT_CONNECTION: True,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert setup_integration.options[CONF_SCAN_INTERVAL] == 60
    assert setup_integration.options[CONF_RECONNECT_INTERVAL] == 120
    assert setup_integration.options[CONF_PERMANENT_CONNECTION] is True


async def test_options_flow_uses_existing_values_as_defaults(hass, setup_integration):
    hass.config_entries.async_update_entry(
        setup_integration,
        options={
            CONF_SCAN_INTERVAL: 120,
            CONF_RECONNECT_INTERVAL: 30,
            CONF_PERMANENT_CONNECTION: True,
        },
    )
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    assert _schema_default(result, CONF_SCAN_INTERVAL) == 120
    assert _schema_default(result, CONF_RECONNECT_INTERVAL) == 30
    assert _schema_default(result, CONF_PERMANENT_CONNECTION) is True
