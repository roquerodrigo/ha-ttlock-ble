from __future__ import annotations

from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.ttlock_ble.connection import connection_signal


async def test_connection_binary_sensor_created_for_each_key(
    hass,
    setup_integration,
) -> None:
    assert len(hass.states.async_all("binary_sensor")) == 1


async def test_connection_binary_sensor_reflects_initial_state(
    hass,
    setup_integration,
) -> None:
    state = hass.states.async_all("binary_sensor")[0]
    assert state.state == "on"


async def test_connection_binary_sensor_device_class(
    hass,
    setup_integration,
) -> None:
    state = hass.states.async_all("binary_sensor")[0]
    assert state.attributes["device_class"] == "connectivity"


async def test_connection_binary_sensor_has_unique_id(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    from homeassistant.helpers import entity_registry as er

    state = hass.states.async_all("binary_sensor")[0]
    registry = er.async_get(hass)
    entry = registry.async_get(state.entity_id)
    assert entry is not None
    assert entry.unique_id == f"{sample_virtual_key.lockMac}_connection"


async def test_connection_binary_sensor_is_diagnostic(
    hass,
    setup_integration,
) -> None:
    from homeassistant.helpers import entity_registry as er

    state = hass.states.async_all("binary_sensor")[0]
    registry = er.async_get(hass)
    entry = registry.async_get(state.entity_id)
    assert entry is not None
    assert entry.entity_category == er.EntityCategory.DIAGNOSTIC


async def test_connection_binary_sensor_updates_on_signal(
    hass,
    setup_integration,
    sample_virtual_key,
    mock_ttlock_connection,
) -> None:
    """A dispatcher signal pushes the freshest connection state without polling."""
    state = hass.states.async_all("binary_sensor")[0]
    assert state.state == "on"
    mock_ttlock_connection.is_connected = False
    async_dispatcher_send(
        hass,
        connection_signal(sample_virtual_key.lockMac),
        False,  # noqa: FBT003
    )
    await hass.async_block_till_done()
    assert hass.states.get(state.entity_id).state == "off"
