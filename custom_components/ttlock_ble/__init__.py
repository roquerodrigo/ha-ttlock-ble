"""TTLock BLE integration for Home Assistant."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, cast

from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import callback

from ttlock_ble import VirtualKey

from .advertisement import TtlockBleAdvertisementTracker
from .connection import TtlockBleConnection
from .const import DEFAULT_SCAN_INTERVAL_SECONDS, DOMAIN
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

    bluetooth_unsubs = TtlockBleAdvertisementTracker(hass, coordinator).async_register(
        virtual_keys,
    )

    async def _stop_connections() -> None:
        for connection in connections.values():
            await connection.async_stop()

    @callback
    def _stop_advertisement_tracking() -> None:
        for unsub in bluetooth_unsubs:
            unsub()

    # Registered before the platforms are forwarded, so a platform that fails
    # to import still gets its connections stopped. Otherwise the entry sits in
    # SETUP_ERROR with one reconnect loop per lock holding the locks' single
    # BLE slots, and each retry stacks another set on top. Callbacks run
    # last-registered-first, so tracking stops before the connections do.
    entry.async_on_unload(_stop_connections)
    entry.async_on_unload(_stop_advertisement_tracking)

    # Trigger the first state refresh without awaiting it, so the config entry
    # can finish loading while connections settle. The task is still tracked by
    # Home Assistant and will be awaited by async_block_till_done in tests and
    # by the startup wrap-up.
    first_refresh = entry.async_create_task(
        hass,
        coordinator.async_refresh(),
        name=f"{DOMAIN}.first_refresh",
    )

    entry.runtime_data = TtlockBleData(
        keys=stored_keys,
        virtual_keys=virtual_keys,
        connections=connections,
        coordinator=coordinator,
        bluetooth_unsubs=bluetooth_unsubs,
        first_refresh=first_refresh,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: TtlockBleConfigEntry,
) -> bool:
    """
    Unload the entities.

    Stopping the connections and the advertisement subscriptions is
    registered on the entry at setup time instead, so it also runs when
    setup itself fails part-way through.
    """
    if entry.runtime_data.first_refresh is not None:
        entry.runtime_data.first_refresh.cancel()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant,
    entry: TtlockBleConfigEntry,
) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
