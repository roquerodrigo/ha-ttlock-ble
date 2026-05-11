from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.integration_blueprint.const import DOMAIN
from custom_components.integration_blueprint.coordinator import (
    IntegrationBlueprintDataUpdateCoordinator,
)
from custom_components.integration_blueprint.exceptions import (
    IntegrationBlueprintApiClientAuthenticationError,
    IntegrationBlueprintApiClientError,
)


def _make_coordinator(hass, payload=None, scan_interval=timedelta(minutes=5)):
    coord = IntegrationBlueprintDataUpdateCoordinator(
        hass=hass, scan_interval=scan_interval
    )
    client = AsyncMock()
    client.async_get_data = AsyncMock(return_value=payload or {})
    runtime_data = type("D", (), {"client": client})()
    entry = type("E", (), {"entry_id": "eid", "runtime_data": runtime_data})()
    coord.config_entry = entry
    return coord, client


def test_init_sets_domain_name(hass):
    coord = IntegrationBlueprintDataUpdateCoordinator(
        hass=hass, scan_interval=timedelta(seconds=300)
    )
    assert coord.name == DOMAIN


def test_init_sets_update_interval(hass):
    coord = IntegrationBlueprintDataUpdateCoordinator(
        hass=hass, scan_interval=timedelta(seconds=42)
    )
    assert coord.update_interval == timedelta(seconds=42)


async def test_update_data_returns_payload(hass, sample_payload):
    coord, _ = _make_coordinator(hass, payload=sample_payload)
    result = await coord._async_update_data()
    assert result == sample_payload


async def test_update_data_raises_update_failed_on_api_error(hass):
    coord, client = _make_coordinator(hass)
    client.async_get_data.side_effect = IntegrationBlueprintApiClientError("down")
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


async def test_update_data_raises_auth_failed_on_auth_error(hass):
    coord, client = _make_coordinator(hass)
    client.async_get_data.side_effect = (
        IntegrationBlueprintApiClientAuthenticationError("nope")
    )
    with pytest.raises(ConfigEntryAuthFailed):
        await coord._async_update_data()
