"""TTLock BLE integration for Home Assistant."""

from __future__ import annotations

from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING, cast

from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import callback
from homeassistant.helpers.device_registry import (
    async_entries_for_config_entry,
    format_mac,
)
from homeassistant.helpers.device_registry import (
    async_get as async_get_device_registry,
)

from ttlock_ble import VirtualKey

from .advertisement import TtlockBleAdvertisementTracker
from .connection import TtlockBleConnection
from .const import (
    CONF_PERMANENT_CONNECTION,
    CONF_RECONNECT_INTERVAL,
    DEFAULT_RECONNECT_INTERVAL_SECONDS,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    LOGGER,
)
from .coordinator import TtlockBleDataUpdateCoordinator
from .data import TtlockBleData, TtlockBleLogCursor
from .record_store import TtlockBleRecordStore

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.device_registry import DeviceEntry

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


def _configured_macs(config: TtlockBleConfigData) -> set[str]:
    """Return the formatted MAC of every lock the entry currently holds."""
    return {format_mac(key["lockMac"]) for key in config["keys"]}


def _device_macs(device: DeviceEntry) -> set[str]:
    """Return the formatted MACs this integration stamped on a device."""
    return {identifier for domain, identifier in device.identifiers if domain == DOMAIN}


@callback
def _async_prune_stale_devices(
    hass: HomeAssistant,
    entry: TtlockBleConfigEntry,
    config: TtlockBleConfigData,
) -> None:
    """
    Drop registry devices whose lock left the entry's key set.

    Reauth and reconfigure replace `keys` wholesale with whatever the
    cloud returns, so a lock removed from the account would otherwise
    linger as a dead device until the user deletes it by hand.
    """
    device_registry = async_get_device_registry(hass)
    configured = _configured_macs(config)
    for device in async_entries_for_config_entry(device_registry, entry.entry_id):
        if not _device_macs(device) & configured:
            LOGGER.info(
                "Removing device %s: its lock is no longer in the entry's keys",
                device.name or device.id,
            )
            device_registry.async_update_device(
                device.id,
                remove_config_entry_id=entry.entry_id,
            )


async def async_remove_config_entry_device(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TtlockBleConfigEntry,
    device_entry: DeviceEntry,
) -> bool:
    """Allow deleting a device once its lock is gone from the entry's keys."""
    config = cast("TtlockBleConfigData", entry.data)
    return not _device_macs(device_entry) & _configured_macs(config)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TtlockBleConfigEntry,
) -> bool:
    """Set up TTLock BLE from a config entry."""
    config = cast("TtlockBleConfigData", entry.data)
    _async_prune_stale_devices(hass, entry, config)
    stored_keys: list[TtlockBleStoredKey] = list(config["keys"])
    virtual_keys = [VirtualKey.from_dict(dict(k)) for k in stored_keys]

    permanent_connection = bool(entry.options.get(CONF_PERMANENT_CONNECTION, False))
    reconnect_cooldown_seconds: float = (
        0.0
        if permanent_connection
        else float(
            entry.options.get(
                CONF_RECONNECT_INTERVAL,
                DEFAULT_RECONNECT_INTERVAL_SECONDS,
            ),
        )
    )
    record_store = TtlockBleRecordStore(hass)
    await record_store.async_load()
    connections: dict[str, TtlockBleConnection] = {
        key.lockMac: TtlockBleConnection(
            hass,
            key,
            reconnect_cooldown_seconds=reconnect_cooldown_seconds,
            log_cursor=TtlockBleLogCursor(
                records=record_store.seen(key.lockMac),
                seeded=record_store.is_seeded(key.lockMac),
                on_move=partial(record_store.async_remember, key.lockMac),
            ),
        )
        for key in virtual_keys
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
