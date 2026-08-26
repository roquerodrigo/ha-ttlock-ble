from __future__ import annotations

from homeassistant.data_entry_flow import FlowResultType

from custom_components.ttlock_ble.const import CONF_PERMANENT_CONNECTION


def _schema_default(result, key):
    schema = result["data_schema"].schema
    schema_key = next(k for k in schema if getattr(k, "schema", k) == key)
    return schema_key.default()


async def test_options_flow_shows_form_with_defaults(hass, setup_integration):
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert _schema_default(result, CONF_PERMANENT_CONNECTION) is False


async def test_permanent_connection_is_the_only_option(hass, setup_integration):
    """Polling and reconnect pacing are gone; nothing else is configurable."""
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    keys = {getattr(k, "schema", k) for k in result["data_schema"].schema}
    assert keys == {CONF_PERMANENT_CONNECTION}


async def test_options_flow_persists_the_option(hass, setup_integration):
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_PERMANENT_CONNECTION: True},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert setup_integration.options[CONF_PERMANENT_CONNECTION] is True


async def test_options_flow_uses_existing_value_as_default(hass, setup_integration):
    hass.config_entries.async_update_entry(
        setup_integration,
        options={CONF_PERMANENT_CONNECTION: True},
    )
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    assert _schema_default(result, CONF_PERMANENT_CONNECTION) is True
