from __future__ import annotations

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.data_entry_flow import FlowResultType

from custom_components.integration_blueprint.const import (
    DEFAULT_SCAN_INTERVAL_SECONDS,
)


async def test_options_flow_shows_form_with_default(hass, setup_integration):
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    schema = result["data_schema"].schema
    scan_interval_key = next(
        k for k in schema if getattr(k, "schema", k) == CONF_SCAN_INTERVAL
    )
    assert scan_interval_key.default() == DEFAULT_SCAN_INTERVAL_SECONDS


async def test_options_flow_persists_scan_interval(hass, setup_integration):
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_SCAN_INTERVAL: 60}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert setup_integration.options[CONF_SCAN_INTERVAL] == 60


async def test_options_flow_uses_existing_value_as_default(hass, setup_integration):
    hass.config_entries.async_update_entry(
        setup_integration, options={CONF_SCAN_INTERVAL: 120}
    )
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    schema = result["data_schema"].schema
    scan_interval_key = next(
        k for k in schema if getattr(k, "schema", k) == CONF_SCAN_INTERVAL
    )
    assert scan_interval_key.default() == 120
