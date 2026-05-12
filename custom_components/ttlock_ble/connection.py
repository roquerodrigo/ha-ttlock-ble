"""
On-demand BLE connection wrapper for ttlock_ble.

Each `TtlockBleConnection` is a one-shot session manager for one
`VirtualKey`. It opens a fresh BLE session for every `async_query_state`,
`async_lock` and `async_unlock`, then tears it down before returning.

This keeps the lock asleep between operations, which TTLock firmware
treats as battery-saving idle. The previous always-on session model was
retired because the reconnect churn was draining the lock's battery.

All public methods serialize through `self._lock` so concurrent callers
(coordinator poll + user command) never overlap on the BLE socket.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from homeassistant.components.bluetooth import async_ble_device_from_address

from ttlock_ble import TTLockClient, TTLockError

from .const import LOGGER

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ttlock_ble import VirtualKey


class TtlockBleConnection:
    """One-shot BLE session manager for a single TTLock lock."""

    def __init__(self, hass: HomeAssistant, key: VirtualKey) -> None:
        """Bind to the HA instance and the credentials for a single lock."""
        self._hass = hass
        self._key = key
        self._lock = asyncio.Lock()

    @property
    def key(self) -> VirtualKey:
        """Return the `VirtualKey` this connection wraps."""
        return self._key

    async def async_query_state(self) -> tuple[int, int | None] | None:
        """Open a fresh BLE session, read `(lock_state, battery)`, close it."""
        async with self._lock:
            client = await self._async_connect()
            if client is None:
                return None
            try:
                return await client.query_state()
            except TTLockError as exc:
                LOGGER.warning(
                    "query_state failed for %s: %s",
                    self._key.lockMac,
                    exc,
                )
                return None
            finally:
                await _async_safe_disconnect(client)

    async def async_lock(self) -> None:
        """Open a fresh BLE session, send LOCK, close it. Raises on failure."""
        await self._async_run_command("lock")

    async def async_unlock(self) -> None:
        """Open a fresh BLE session, send UNLOCK, close it. Raises on failure."""
        await self._async_run_command("unlock")

    async def _async_run_command(self, action: str) -> None:
        """Acquire the lock, open a fresh BLE session, run command, close it."""
        async with self._lock:
            client = await self._async_connect()
            if client is None:
                msg = f"Lock {self._key.lockMac} not reachable via Bluetooth"
                raise TTLockError(msg)
            try:
                if action == "lock":
                    await client.lock()
                else:
                    await client.unlock()
            except TimeoutError as exc:
                msg = f"Lock {self._key.lockMac} timed out responding to {action}"
                raise TTLockError(msg) from exc
            finally:
                await _async_safe_disconnect(client)

    async def _async_connect(self) -> TTLockClient | None:
        """Open a fresh BLE session. Caller must hold `self._lock`."""
        device = async_ble_device_from_address(
            self._hass,
            self._key.lockMac,
            connectable=True,
        )
        if device is None:
            return None
        client = TTLockClient.from_ble_device(device, self._key)
        try:
            await client.connect()
        except TTLockError as exc:
            LOGGER.debug("BLE connect failed for %s: %s", self._key.lockMac, exc)
            return None
        return client


async def _async_safe_disconnect(client: TTLockClient) -> None:
    """Tear down a BLE client, swallowing transport-layer noise."""
    with contextlib.suppress(Exception):
        await client.disconnect()
