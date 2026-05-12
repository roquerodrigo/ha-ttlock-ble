"""TTLock BLE integration for Home Assistant."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, cast

from homeassistant.const import CONF_SCAN_INTERVAL, Platform

from ttlock_ble import VirtualKey

from .connection import TtlockBleConnection
from .const import DEFAULT_SCAN_INTERVAL_SECONDS
from .coordinator import TtlockBleDataUpdateCoordinator
from .data import TtlockBleData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import (
        TtlockBleConfigData,
        TtlockBleConfigEntry,
        TtlockBleStoredKey,
    )

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.LOCK,
    Platform.SENSOR,
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TtlockBleConfigEntry,
) -> bool:
    """Set up TTLock BLE from a config entry."""
    config = cast("TtlockBleConfigData", entry.data)
    stored_keys: list[TtlockBleStoredKey] = list(config["keys"])
    virtual_keys = [VirtualKey.from_dict(dict(k)) for k in stored_keys]

    connections: dict[str, TtlockBleConnection] = {
        key.lockMac: TtlockBleConnection(hass, key) for key in virtual_keys
    }

    scan_interval_seconds: int = int(
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS),
    )
    coordinator = TtlockBleDataUpdateCoordinator(
        hass=hass,
        scan_interval=timedelta(seconds=scan_interval_seconds),
        connections=connections,
    )

    entry.runtime_data = TtlockBleData(
        keys=stored_keys,
        virtual_keys=virtual_keys,
        connections=connections,
        coordinator=coordinator,
    )
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: TtlockBleConfigEntry,
) -> bool:
    """Tear down entities. No long-lived BLE sessions to stop."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant,
    entry: TtlockBleConfigEntry,
) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
