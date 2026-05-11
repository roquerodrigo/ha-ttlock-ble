"""Diagnostics support for integration_blueprint."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.core import HomeAssistant

    from .data import (
        IntegrationBlueprintConfigEntry,
        IntegrationBlueprintDiagnosticsEntry,
        IntegrationBlueprintDiagnosticsPayload,
    )

TO_REDACT: frozenset[str] = frozenset({CONF_PASSWORD, CONF_USERNAME})


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001
    entry: IntegrationBlueprintConfigEntry,
) -> IntegrationBlueprintDiagnosticsPayload:
    """Return diagnostics for a config entry."""
    redacted_data = cast(
        "Mapping[str, str]",
        async_redact_data(dict(entry.data), set(TO_REDACT)),
    )
    redacted_options = cast(
        "Mapping[str, str | int]",
        async_redact_data(dict(entry.options), set(TO_REDACT)),
    )
    diag_entry: IntegrationBlueprintDiagnosticsEntry = {
        "title": entry.title,
        "version": entry.version,
        "domain": entry.domain,
        "data": redacted_data,
        "options": redacted_options,
    }
    return {
        "entry": diag_entry,
        "coordinator_data": entry.runtime_data.coordinator.data,
    }
