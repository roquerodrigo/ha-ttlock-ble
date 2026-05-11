from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.integration_blueprint.sensor import (
    ENTITY_DESCRIPTIONS,
    IntegrationBlueprintSensor,
)

SAMPLE_POST = {
    "userId": 1,
    "id": 1,
    "title": "hello",
    "body": "world",
}


def _make_sensor(data=None) -> IntegrationBlueprintSensor:
    coord = MagicMock()
    coord.data = data
    coord.config_entry.entry_id = "eid"
    return IntegrationBlueprintSensor(
        coordinator=coord, entity_description=ENTITY_DESCRIPTIONS[0]
    )


async def test_sensor_count(hass, setup_integration):
    assert len(hass.states.async_all("sensor")) == 1


async def test_sensor_state_value(hass, setup_integration):
    state = next(iter(hass.states.async_all("sensor")))
    assert state.state == "sunt aut facere repellat provident"


def test_native_value_extracts_title():
    sensor = _make_sensor(data=SAMPLE_POST)
    assert sensor.native_value == "hello"


def test_native_value_returns_none_before_first_refresh():
    sensor = _make_sensor(data=None)
    assert sensor.native_value is None


def test_unique_id_combines_entry_id_and_key():
    sensor = _make_sensor()
    assert sensor.unique_id == "eid_integration_blueprint"
