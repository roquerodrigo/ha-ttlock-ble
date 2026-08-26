"""Diagnostics support for ttlock_ble."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from ttlock_ble import LockAdvertisement

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.core import HomeAssistant

    from .data import (
        TtlockBleConfigData,
        TtlockBleConfigEntry,
        TtlockBleDiagnosticsAdvertisement,
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
    hass: HomeAssistant,
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
        "title": _redacted_title(entry),
        "version": entry.version,
        "domain": entry.domain,
        "data": redacted_data,
        "options": redacted_options,
    }
    locks: list[TtlockBleDiagnosticsLockSummary] = [
        _summarize_key(key) for key in entry.runtime_data.keys
    ]
    coordinator = entry.runtime_data.coordinator
    coordinator_state = coordinator.data or {}
    return {
        "entry": diag_entry,
        "locks": locks,
        "coordinator_state": dict(coordinator_state),
        "advertisements": {
            key["lockMac"]: _summarize_advertisement(hass, key["lockMac"])
            for key in entry.runtime_data.keys
        },
        "device_descriptions": {
            key["lockMac"]: coordinator.async_device_description(key["lockMac"])
            for key in entry.runtime_data.keys
        },
    }


def _redacted_title(entry: TtlockBleConfigEntry) -> str:
    """
    Return the entry title, redacted when it is the cloud account name.

    A cloud entry is titled with the username, so copying the title
    verbatim reinstated the address that `TO_REDACT` removes from
    `entry.data` one level below — into the dump the bug template asks
    users to attach to public issues. A manual entry is titled with the
    lock alias and carries nothing sensitive.
    """
    config = cast("TtlockBleConfigData", cast("object", entry.data))
    return REDACTED if "username" in config else entry.title


def _summarize_advertisement(
    hass: HomeAssistant,
    mac: str,
) -> TtlockBleDiagnosticsAdvertisement | None:
    """Capture the last advertisement seen for `mac`, raw bytes included."""
    service_info = async_last_service_info(hass, mac, connectable=False)
    if service_info is None:
        return None
    decoded: dict[str, str | int | bool | None] | None = None
    for company_id, payload in service_info.manufacturer_data.items():
        advertisement = LockAdvertisement.from_manufacturer_data(company_id, payload)
        if advertisement is not None:
            decoded = {
                "protocol_type": advertisement.protocol_type,
                "protocol_version": advertisement.protocol_version,
                "scene": advertisement.scene,
                "lock_state": (
                    None
                    if advertisement.lock_state is None
                    else advertisement.lock_state.name
                ),
                "has_new_records": advertisement.has_new_records,
                "is_setting_mode": advertisement.is_setting_mode,
                "is_dormant": advertisement.is_dormant,
                "battery": advertisement.battery,
                "lock_mac": advertisement.lock_mac,
            }
            break
    return {
        "source": service_info.source,
        "rssi": service_info.rssi,
        "manufacturer_data": {
            str(company_id): payload.hex()
            for company_id, payload in service_info.manufacturer_data.items()
        },
        "decoded": decoded,
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
