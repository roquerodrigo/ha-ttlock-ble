"""TTLock BLE integration for Home Assistant."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, cast

from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
    async_register_callback,
)
from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import callback

from ttlock_ble import VirtualKey

from .connection import TtlockBleConnection
from .const import DEFAULT_SCAN_INTERVAL_SECONDS
from .coordinator import TtlockBleDataUpdateCoordinator
from .data import TtlockBleData

if TYPE_CHECKING:
    from homeassistant.components.bluetooth import (
        BluetoothChange,
        BluetoothServiceInfoBleak,
    )
    from homeassistant.core import CALLBACK_TYPE, HomeAssistant

    from .data import (
        TtlockBleConfigData,
        TtlockBleConfigEntry,
        TtlockBleStoredKey,
    )

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.EVENT,
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
    for connection in connections.values():
        await connection.async_start()

    scan_interval_seconds: int = int(
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS),
    )
    coordinator = TtlockBleDataUpdateCoordinator(
        hass=hass,
        scan_interval=timedelta(seconds=scan_interval_seconds),
        connections=connections,
    )

    bluetooth_unsubs = _async_register_bluetooth_callbacks(
        hass,
        virtual_keys,
        coordinator,
    )

    entry.runtime_data = TtlockBleData(
        keys=stored_keys,
        virtual_keys=virtual_keys,
        connections=connections,
        coordinator=coordinator,
        bluetooth_unsubs=bluetooth_unsubs,
    )
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


@callback
def _async_register_bluetooth_callbacks(
    hass: HomeAssistant,
    virtual_keys: list[VirtualKey],
    coordinator: TtlockBleDataUpdateCoordinator,
) -> list[CALLBACK_TYPE]:
    """
    Refresh the coordinator the moment HA's bluetooth manager sees a lock.

    Without this the coordinator only re-polls every `scan_interval`, so the
    entity can spend many minutes `unavailable` after HA boots — HA's bluetooth
    discovery typically lags integration setup by 30-120 seconds. Subscribing
    per-MAC lets the UI become available within seconds of the first
    advertisement.
    """

    @callback
    def _on_advertisement(
        _service_info: BluetoothServiceInfoBleak,
        _change: BluetoothChange,
    ) -> None:
        hass.async_create_task(coordinator.async_request_refresh())

    return [
        async_register_callback(
            hass,
            _on_advertisement,
            BluetoothCallbackMatcher(address=key.lockMac, connectable=True),
            BluetoothScanningMode.ACTIVE,
        )
        for key in virtual_keys
    ]


async def async_unload_entry(
    hass: HomeAssistant,
    entry: TtlockBleConfigEntry,
) -> bool:
    """Tear down entities and stop the per-lock BLE connections."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    for unsub in entry.runtime_data.bluetooth_unsubs:
        unsub()
    for connection in entry.runtime_data.connections.values():
        await connection.async_stop()
    return unloaded


async def async_reload_entry(
    hass: HomeAssistant,
    entry: TtlockBleConfigEntry,
) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
