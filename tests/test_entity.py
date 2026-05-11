from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.integration_blueprint.const import ATTRIBUTION, DOMAIN
from custom_components.integration_blueprint.entity import IntegrationBlueprintEntity


def _make_entity(entry_id="test_entry_id") -> IntegrationBlueprintEntity:
    coordinator = MagicMock()
    coordinator.config_entry.entry_id = entry_id
    return IntegrationBlueprintEntity(coordinator=coordinator)


def test_attribution():
    assert _make_entity()._attr_attribution == ATTRIBUTION


def test_has_entity_name():
    assert _make_entity()._attr_has_entity_name is True


def test_device_info_name():
    assert _make_entity().device_info["name"] == "Integration Blueprint"


def test_device_info_manufacturer():
    assert _make_entity().device_info["manufacturer"] == "Integration Blueprint"


def test_device_info_identifiers_contain_domain():
    assert any(DOMAIN in str(i) for i in _make_entity().device_info["identifiers"])


def test_device_info_identifiers_contain_entry_id():
    assert any(
        "my_id" in str(i) for i in _make_entity("my_id").device_info["identifiers"]
    )


def test_coordinator_stored():
    coord = MagicMock()
    coord.config_entry.entry_id = "eid"
    assert IntegrationBlueprintEntity(coordinator=coord).coordinator is coord
