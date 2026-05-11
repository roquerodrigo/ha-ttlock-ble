"""Custom types for integration_blueprint."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, NotRequired, TypedDict

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import IntegrationBlueprintApiClient
    from .coordinator import IntegrationBlueprintDataUpdateCoordinator


type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list[JsonValue] | Mapping[str, JsonValue]
type JsonObject = Mapping[str, JsonValue]


class IntegrationBlueprintPost(TypedDict):
    """Shape of a /posts/{id} response from jsonplaceholder."""

    userId: int
    id: int
    title: str
    body: str


class IntegrationBlueprintConfigData(TypedDict):
    """Shape of the credentials persisted on the config entry."""

    username: str
    password: str


class IntegrationBlueprintOptionsData(TypedDict, total=False):
    """Shape of the options writable by the options flow."""

    scan_interval: NotRequired[int]


class IntegrationBlueprintDiagnosticsEntry(TypedDict):
    """Entry section of the diagnostics dump."""

    title: str
    version: int
    domain: str
    data: Mapping[str, str]
    options: Mapping[str, str | int]


class IntegrationBlueprintDiagnosticsPayload(TypedDict):
    """Top-level shape returned by async_get_config_entry_diagnostics."""

    entry: IntegrationBlueprintDiagnosticsEntry
    coordinator_data: IntegrationBlueprintPost | None


type IntegrationBlueprintConfigEntry = ConfigEntry[IntegrationBlueprintData]


@dataclass
class IntegrationBlueprintData:
    """Data stored on entry.runtime_data for the Integration Blueprint."""

    client: IntegrationBlueprintApiClient
    coordinator: IntegrationBlueprintDataUpdateCoordinator
    integration: Integration
