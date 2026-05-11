"""Diagnostics support for ttlock_ble."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.core import HomeAssistant

    from .data import (
        TtlockBleConfigEntry,
        TtlockBleDiagnosticsEntry,
        TtlockBleDiagnosticsLockSummary,
        TtlockBleDiagnosticsPayload,
        TtlockBleStoredKey,
    )

TO_REDACT: frozenset[str] = frozenset(
    {
        CONF_PASSWORD,
        CONF_USERNAME,
        "aesKeyStr",
        "unlockKey",
        "adminPs",
        "keys",
    },
)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TtlockBleConfigEntry,
) -> TtlockBleDiagnosticsPayload:
    """Return diagnostics for a config entry."""
    redacted_data = cast(
        "Mapping[str, str | int]",
        async_redact_data(dict(entry.data), set(TO_REDACT)),
    )
    redacted_options = cast(
        "Mapping[str, str | int]",
        async_redact_data(dict(entry.options), set(TO_REDACT)),
    )
    diag_entry: TtlockBleDiagnosticsEntry = {
        "title": entry.title,
        "version": entry.version,
        "domain": entry.domain,
        "data": redacted_data,
        "options": redacted_options,
    }
    locks: list[TtlockBleDiagnosticsLockSummary] = [
        _summarize_key(key) for key in entry.runtime_data.keys
    ]
    coordinator_state = entry.runtime_data.coordinator.data or {}
    return {
        "entry": diag_entry,
        "locks": locks,
        "coordinator_state": dict(coordinator_state),
    }


def _summarize_key(key: TtlockBleStoredKey) -> TtlockBleDiagnosticsLockSummary:
    """Project a stored key onto the non-sensitive subset shown in diagnostics."""
    return {
        "lockId": key["lockId"],
        "lockMac": key["lockMac"],
        "lockAlias": key["lockAlias"],
        "lockName": key["lockName"],
        "keyType": key["keyType"],
        "userType": key["userType"],
    }
