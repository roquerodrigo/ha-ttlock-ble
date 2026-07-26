"""
DataUpdateCoordinator for ttlock_ble.

Reads lock state through the per-lock `TtlockBleConnection` (which keeps
a persistent BLE session and pushes events out-of-band). The
coordinator only owns the periodic state refresh; it does not open BLE
connections itself.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, LOGGER

if TYPE_CHECKING:
    from datetime import timedelta

    from homeassistant.core import HomeAssistant

    from .connection import TtlockBleConnection
    from .data import (
        TtlockBleConfigEntry,
        TtlockBleCoordinatorData,
        TtlockBleLockState,
    )


LOCK_STATE_LOCKED = 0
LOCK_STATE_UNLOCKED = 1


class TtlockBleDataUpdateCoordinator(DataUpdateCoordinator["TtlockBleCoordinatorData"]):
    """Periodically poll BLE state via each lock's persistent connection."""

    config_entry: TtlockBleConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        scan_interval: timedelta,
        connections: dict[str, TtlockBleConnection],
    ) -> None:
        """Pin the polling interval and the per-MAC connection map."""
        super().__init__(
            hass=hass,
            logger=LOGGER,
            name=DOMAIN,
            update_interval=scan_interval,
        )
        self._connections = connections
        self._first_refresh_done = False

    @property
    def connections(self) -> dict[str, TtlockBleConnection]:
        """Return the per-MAC connection map this coordinator polls."""
        return self._connections

    async def _async_update_data(self) -> TtlockBleCoordinatorData:
        """Poll every connection once and return the aggregated state map."""
        poll_tasks = {
            mac: self._async_poll(connection)
            for mac, connection in self._connections.items()
        }
        results = await asyncio.gather(*poll_tasks.values(), return_exceptions=True)
        self._first_refresh_done = True
        state: TtlockBleCoordinatorData = {}
        for mac, result in zip(poll_tasks, results, strict=True):
            if isinstance(result, BaseException):
                LOGGER.warning("Failed to poll %s: %s", mac, result)
                state[mac] = {
                    "locked": None,
                    "battery_level": None,
                    "available": False,
                }
            else:
                state[mac] = result
        return state

    async def _async_poll(
        self,
        connection: TtlockBleConnection,
    ) -> TtlockBleLockState:
        """Query one lock through its persistent connection."""
        result = await connection.async_query_state()
        if result is None:
            return {"locked": None, "battery_level": None, "available": False}
        raw_state, battery = result
        await connection.async_get_operation_log(
            dispatch=self._first_refresh_done,
        )
        return {
            "locked": _parse_lock_state(raw_state),
            "battery_level": battery,
            "available": True,
        }


def _parse_lock_state(raw: int | None) -> bool | None:
    """Translate the SDK's tri-state lock value into HA's `bool | None`."""
    if raw == LOCK_STATE_LOCKED:
        return True
    if raw == LOCK_STATE_UNLOCKED:
        return False
    return None
