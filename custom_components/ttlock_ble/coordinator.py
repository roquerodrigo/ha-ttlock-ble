"""
DataUpdateCoordinator for ttlock_ble.

Reads lock state through the per-lock `TtlockBleConnection` (which keeps
a persistent BLE session and pushes events out-of-band). The
coordinator only owns the periodic state refresh; it does not open BLE
connections itself.

State also arrives without any poll: `async_apply_advertisement`
publishes what `TtlockBleAdvertisementTracker` decodes from the lock's
advertisements, which is the only channel that reports an auto-lock.
The same advertisements announce that the lock has unsynced operation
records, and that flag is what schedules an out-of-band log read.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ttlock_ble import LockState

from .const import DOMAIN, LOGGER

if TYPE_CHECKING:
    from datetime import timedelta

    from homeassistant.core import HomeAssistant

    from ttlock_ble import LockAdvertisement

    from .connection import TtlockBleConnection
    from .data import (
        TtlockBleConfigEntry,
        TtlockBleCoordinatorData,
        TtlockBleLockState,
    )


LOCK_STATE_LOCKED = 0
LOCK_STATE_UNLOCKED = 1

# How long to leave a lock alone between operation-log reads while it
# keeps advertising unsynced records. Reaching an idle lock takes several
# connect attempts, so reads have to be spaced or the adapter would be
# busy for as long as the records stay unread.
LOG_RETRY_COOLDOWN_SECONDS = 300.0


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
        self._log_fetches: set[str] = set()
        self._log_retry_after: dict[str, float] = {}

    @property
    def connections(self) -> dict[str, TtlockBleConnection]:
        """Return the per-MAC connection map this coordinator polls."""
        return self._connections

    @callback
    def async_has_state(self, mac: str) -> bool:
        """Report whether a lock state has ever been read for `mac`, by any channel."""
        snapshot = (self.data or {}).get(mac)
        return snapshot is not None and snapshot.get("locked") is not None

    @callback
    def async_apply_advertisement(
        self,
        mac: str,
        advertisement: LockAdvertisement,
    ) -> None:
        """
        Publish state decoded from a BLE advertisement, without polling the lock.

        Also reschedules the next poll: a lock that keeps advertising
        reports itself for free, so there is nothing to connect for.

        A dormant advertisement carries no bolt position — the firmware
        clears that bit along with the radio, so the payload is
        indistinguishable from a locked one — and only its battery is
        adopted, leaving whatever state was last known in place. The
        poll is still rescheduled: an idle lock takes several connect
        attempts to reach, and its own advertisements report the state
        again as soon as it wakes.
        """
        state_name = (
            "UNKNOWN"
            if advertisement.lock_state is None
            else advertisement.lock_state.name
        )
        LOGGER.debug(
            "Advertised state for %s (lock_state=%s battery=%d dormant=%s)",
            mac,
            state_name,
            advertisement.battery,
            advertisement.is_dormant,
        )
        previous = (self.data or {}).get(mac) or {}
        locked = (
            previous.get("locked")
            if advertisement.lock_state is None
            else advertisement.lock_state is LockState.LOCKED
        )
        snapshot: TtlockBleLockState = {
            "locked": locked,
            "battery_level": advertisement.battery,
        }
        self.async_set_updated_data({**(self.data or {}), mac: snapshot})
        self._async_sync_operation_log(mac, advertisement)

    @callback
    def _async_sync_operation_log(
        self,
        mac: str,
        advertisement: LockAdvertisement,
    ) -> None:
        """
        Read the operation log while the lock advertises unsynced records.

        The lock raises this flag for anything it recorded and lowers it
        once its cursor is synced, so it doubles as the acknowledgement:
        a read that worked is visible as the flag going away, and one
        that did not is visible as it staying up. Reacting to the level
        rather than to its rising edge is what makes that usable —
        `async_get_operation_log` reports an unreachable lock by
        returning nothing rather than by raising, so an edge would be
        consumed by a read that never happened and the record would sit
        there until something else went looking for it.

        `_log_retry_after` keeps the level from becoming a session per
        advertisement: one read is started, and the next is not
        considered until the cooldown expires. Seeing the flag down
        clears it, so a record written right after a successful read is
        still picked up immediately rather than waiting out a cooldown
        it has no reason to serve.

        Dormancy is not a reason to skip. A lock that went back to sleep
        still advertises what it holds, and that is the common case for
        anything done at the door: reaching it then costs several
        connect attempts, but it does answer.
        """
        if not advertisement.has_new_records:
            self._log_retry_after.pop(mac, None)
            return
        connection = self._connections.get(mac)
        if connection is None or mac in self._log_fetches:
            return
        now = time.monotonic()
        if now < self._log_retry_after.get(mac, 0.0):
            return
        self._log_retry_after[mac] = now + LOG_RETRY_COOLDOWN_SECONDS
        self._log_fetches.add(mac)
        self.config_entry.async_create_task(
            self.hass,
            self._async_fetch_operation_log(mac, connection),
            name=f"{DOMAIN}.advertised_operation_log.{mac}",
        )

    async def _async_fetch_operation_log(
        self,
        mac: str,
        connection: TtlockBleConnection,
    ) -> None:
        """Read the log once so the connection dispatches whatever is new."""
        LOGGER.debug("Advertised records pending for %s, reading the log", mac)
        try:
            await connection.async_get_operation_log()
        except Exception:  # noqa: BLE001
            # Reaching an idle lock takes several attempts, so a failed
            # read is routine; the lock keeps advertising the records
            # until one of them lands.
            LOGGER.debug(
                "Advertised operation-log read failed for %s",
                mac,
                exc_info=True,
            )
        finally:
            self._log_fetches.discard(mac)

    async def _async_update_data(self) -> TtlockBleCoordinatorData:
        """Poll every connection once and return the aggregated state map."""
        poll_tasks = {
            mac: self._async_poll(connection)
            for mac, connection in self._connections.items()
        }
        results = await asyncio.gather(*poll_tasks.values(), return_exceptions=True)
        state: TtlockBleCoordinatorData = {}
        for mac, result in zip(poll_tasks, results, strict=True):
            if isinstance(result, BaseException):
                LOGGER.warning("Failed to poll %s: %s", mac, result)
                state[mac] = {"locked": None, "battery_level": None}
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
            return {"locked": None, "battery_level": None}
        raw_state, battery = result
        try:
            await connection.async_get_operation_log()
        except Exception:  # noqa: BLE001
            # The log feeds the event entity only. Failing the poll here
            # would throw away the state and battery already read, and the
            # entity would keep whatever HA last wrote optimistically —
            # a confidently wrong value that silently disables any
            # state-based automation built on it.
            LOGGER.debug(
                "Operation log read failed for %s; keeping the state read",
                connection.key.lockMac,
                exc_info=True,
            )
        return {
            "locked": _parse_lock_state(raw_state),
            "battery_level": battery,
        }


def _parse_lock_state(raw: int | None) -> bool | None:
    """Translate the SDK's tri-state lock value into HA's `bool | None`."""
    if raw == LOCK_STATE_LOCKED:
        return True
    if raw == LOCK_STATE_UNLOCKED:
        return False
    return None
