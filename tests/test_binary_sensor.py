from __future__ import annotations

from unittest.mock import MagicMock, patch


async def test_presence_binary_sensor_created_for_each_key(
    hass,
    setup_integration,
) -> None:
    assert len(hass.states.async_all("binary_sensor")) == 1


async def test_presence_binary_sensor_device_class(
    hass,
    setup_integration,
) -> None:
    state = hass.states.async_all("binary_sensor")[0]
    assert state.attributes["device_class"] == "connectivity"


async def test_presence_binary_sensor_has_unique_id(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    from homeassistant.helpers import entity_registry as er

    state = hass.states.async_all("binary_sensor")[0]
    registry = er.async_get(hass)
    entry = registry.async_get(state.entity_id)
    assert entry is not None
    assert entry.unique_id == f"{sample_virtual_key.lockMac}_presence"


async def test_presence_binary_sensor_is_diagnostic(
    hass,
    setup_integration,
) -> None:
    from homeassistant.helpers import entity_registry as er

    state = hass.states.async_all("binary_sensor")[0]
    registry = er.async_get(hass)
    entry = registry.async_get(state.entity_id)
    assert entry is not None
    assert entry.entity_category == er.EntityCategory.DIAGNOSTIC


async def test_presence_binary_sensor_reads_address_present(
    hass,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    """`is_on` mirrors `async_address_present` from HA's bluetooth manager."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    with patch(
        "custom_components.ttlock_ble.binary_sensor.async_address_present",
        return_value=True,
    ):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"username": "u", "password": "p", "keys": [sample_stored_key]},
            unique_id="u",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        state = hass.states.async_all("binary_sensor")[0]
        assert state.state == "on"
        assert state.attributes["icon"] == "mdi:bluetooth"


async def test_presence_binary_sensor_off_when_not_advertising(
    hass,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    with patch(
        "custom_components.ttlock_ble.binary_sensor.async_address_present",
        return_value=False,
    ):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"username": "u", "password": "p", "keys": [sample_stored_key]},
            unique_id="u",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        state = hass.states.async_all("binary_sensor")[0]
        assert state.state == "off"
        assert state.attributes["icon"] == "mdi:bluetooth-off"


async def test_presence_binary_sensor_registers_bluetooth_callbacks(
    hass,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    """Entity registers an advertisement callback and an unavailable tracker."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    with (
        patch(
            "custom_components.ttlock_ble.binary_sensor.async_register_callback",
            return_value=MagicMock(),
        ) as reg,
        patch(
            "custom_components.ttlock_ble.binary_sensor.async_track_unavailable",
            return_value=MagicMock(),
        ) as track,
    ):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"username": "u", "password": "p", "keys": [sample_stored_key]},
            unique_id="u",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert reg.call_count == 1
        assert track.call_count == 1


async def test_presence_binary_sensor_callbacks_refresh_state(
    hass,
    sample_stored_key,
    enable_bluetooth,
    enable_custom_integrations,
    mock_cloud,
    mock_ttlock_connection,
) -> None:
    """Advertisement + unavailable callbacks both push a fresh state."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    captured_ad: list = []
    captured_un: list = []

    def _capture_register(_hass, callback, *_args, **_kwargs):
        captured_ad.append(callback)
        return MagicMock()

    def _capture_track(_hass, callback, *_args, **_kwargs):
        captured_un.append(callback)
        return MagicMock()

    with (
        patch(
            "custom_components.ttlock_ble.binary_sensor.async_register_callback",
            side_effect=_capture_register,
        ),
        patch(
            "custom_components.ttlock_ble.binary_sensor.async_track_unavailable",
            side_effect=_capture_track,
        ),
        patch(
            "custom_components.ttlock_ble.binary_sensor.async_address_present",
            return_value=True,
        ) as presence,
    ):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"username": "u", "password": "p", "keys": [sample_stored_key]},
            unique_id="u",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        state = hass.states.async_all("binary_sensor")[0]
        assert state.state == "on"
        presence.return_value = False
        captured_ad[0](MagicMock(), MagicMock())
        await hass.async_block_till_done()
        assert hass.states.get(state.entity_id).state == "off"
        presence.return_value = True
        captured_un[0](MagicMock())
        await hass.async_block_till_done()
        assert hass.states.get(state.entity_id).state == "on"
