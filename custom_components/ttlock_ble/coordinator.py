"""
DataUpdateCoordinator for ttlock_ble.

State arrives without opening anything: `async_apply_advertisement`
publishes what `TtlockBleAdvertisementTracker` decodes from the lock's
advertisements, which is also the only channel that reports an
auto-lock. The same advertisements announce that the lock holds
unsynced operation records, and that flag is what schedules a log read.

There is no polling interval. A refresh happens only when something
asks for one — today that is the lock entity, right after a command,
while the session it opened is still up.
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.device_registry import (
    async_get as async_get_device_registry,
)
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from ttlock_ble import LockState

from .const import DOMAIN, LOGGER

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.core import CALLBACK_TYPE, HomeAssistant

    from ttlock_ble import LockAdvertisement

    from .clock_sync_store import TtlockBleClockSyncStore
    from .connection import TtlockBleConnection
    from .data import (
        TtlockBleClockSync,
        TtlockBleConfigEntry,
        TtlockBleCoordinatorData,
        TtlockBleDeviceDescription,
        TtlockBleLockState,
    )
    from .device_description_store import TtlockBleDeviceDescriptionStore


LOCK_STATE_LOCKED = 0
LOCK_STATE_UNLOCKED = 1

# How long to leave a lock alone between operation-log reads while it
# keeps advertising unsynced records. Reaching an idle lock takes several
# connect attempts, so reads have to be spaced or the adapter would be
# busy for as long as the records stay unread.
LOG_RETRY_COOLDOWN_SECONDS = 300.0

# How long to leave a lock alone between attempts to read a bolt position
# nothing has reported yet. Long enough that a lock which keeps refusing
# is not connected to on every advertisement it sends.
STATE_PROBE_COOLDOWN_SECONDS = 300.0

# How long between comparisons of a lock's clock against local time. The
# lock has no NTP and drifts by seconds a day, so checking more often
# than this spends a BLE round trip to learn nothing.
CLOCK_CHECK_INTERVAL_SECONDS = 24 * 60 * 60

# How far off the lock's clock has to read before it is written back.
# Deliberately far above the two seconds the library defaults to: the
# measurement travels over BLE, and the round trip alone accounts for
# seconds, so a tighter threshold would rewrite a healthy lock's clock
# on every check and pay for it in battery.
CLOCK_DRIFT_THRESHOLD_SECONDS = 30.0

# Above this, a correction is worth a line in the log at INFO. A lock
# does not drift by minutes on its own - a gap that size usually means
# it was set up on a different wall clock than Home Assistant keeps.
CLOCK_LARGE_CORRECTION_SECONDS = 300.0


class TtlockBleDataUpdateCoordinator(DataUpdateCoordinator["TtlockBleCoordinatorData"]):
    """Publish lock state, from advertisements and from on-demand reads."""

    config_entry: TtlockBleConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        connections: dict[str, TtlockBleConnection],
        descriptions: TtlockBleDeviceDescriptionStore,
        clock_syncs: TtlockBleClockSyncStore,
    ) -> None:
        """
        Pin the per-MAC connection map. No polling interval on purpose.

        `update_interval` is left unset: a refresh opens a BLE session,
        and everything a poll used to provide now arrives without one.
        State and battery come from the lock's advertisements, and the
        operation log is read when the lock itself says it has records.
        A refresh still runs on demand, right after a command, while the
        session that carried the command is open anyway.
        """
        super().__init__(hass=hass, logger=LOGGER, name=DOMAIN)
        self._connections = connections
        self._descriptions = descriptions
        self._clock_syncs = clock_syncs
        self._described: set[str] = set()
        self._log_fetches: set[str] = set()
        self._records_pending: dict[str, bool] = {}
        self._log_retries: dict[str, CALLBACK_TYPE] = {}
        self._state_probes: dict[str, CALLBACK_TYPE] = {}

    async def async_shutdown(self) -> None:
        """
        Cancel the pending timers along with the coordinator itself.

        Neither timer is cancelled by anything else, and the log retry
        re-arms itself while the lock still advertises unsynced records
        - a flag only an advertisement lowers, and the subscription that
        would deliver one is gone by the time an entry unloads. Left
        armed, the retry outlives the entry it belongs to, keeps a
        stopped connection and the whole entry alive with it, and logs
        against a lock the user may have removed, every cooldown, for
        the rest of the Home Assistant run.
        """
        for cancel in self._log_retries.values():
            cancel()
        self._log_retries.clear()
        for cancel in self._state_probes.values():
            cancel()
        self._state_probes.clear()
        await super().async_shutdown()

    @property
    def connections(self) -> dict[str, TtlockBleConnection]:
        """Return the per-MAC connection map this coordinator polls."""
        return self._connections

    @callback
    def async_device_description(self, mac: str) -> TtlockBleDeviceDescription | None:
        """Return the hardware strings `mac` last reported about itself."""
        return self._descriptions.get(mac)

    @callback
    def async_clock_sync(self, mac: str) -> TtlockBleClockSync | None:
        """Return the last clock comparison for `mac`, if there was one."""
        return self._clock_syncs.get(mac)

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
        self.async_note_lock_seen(mac)

    @callback
    def async_note_lock_seen(self, mac: str) -> None:
        """
        Read the bolt position over BLE while nothing has reported one.

        An advertisement carries the bolt position only while the lock is
        awake; a dormant one clears that bit along with the radio. A lock
        that has not been awake since Home Assistant started therefore
        has no position anyone can state, and nothing else will produce
        one until someone touches the door.

        Being heard at all is the useful signal here: it means the lock
        is in range, which is the one moment a connect is worth trying.
        The attempt is rate-limited because it is worth trying, not worth
        repeating — a dormant lock takes several connects to answer, and
        this must not turn every advertisement into one.
        """
        if self.async_has_state(mac):
            self._async_cancel_state_probe(mac)
            return
        if mac not in self._connections or mac in self._state_probes:
            return
        self._state_probes[mac] = async_call_later(
            self.hass,
            STATE_PROBE_COOLDOWN_SECONDS,
            partial(self._async_clear_state_probe, mac),
        )
        LOGGER.debug("No bolt position known for %s, reading it over BLE", mac)
        self.config_entry.async_create_task(
            self.hass,
            self.async_request_refresh(),
            name=f"{DOMAIN}.state_probe.{mac}",
        )

    @callback
    def _async_clear_state_probe(self, mac: str, _now: datetime) -> None:
        """Let the next advertisement try again."""
        self._state_probes.pop(mac, None)

    @callback
    def _async_cancel_state_probe(self, mac: str) -> None:
        """Drop the rate limit once the position is known."""
        cancel = self._state_probes.pop(mac, None)
        if cancel is not None:
            cancel()

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
        self._records_pending[mac] = advertisement.has_new_records
        if not advertisement.has_new_records:
            self._async_cancel_log_retry(mac)
            return
        self._async_read_log_if_due(mac)

    @callback
    def _async_read_log_if_due(self, mac: str) -> None:
        """
        Start a log read for `mac` unless one is running or a retry is armed.

        The armed timer is the pacing: while it is pending the lock is
        deliberately left alone, so further advertisements do not turn
        the level into a BLE session apiece.
        """
        connection = self._connections.get(mac)
        if connection is None or mac in self._log_fetches or mac in self._log_retries:
            return
        self._log_fetches.add(mac)
        self.config_entry.async_create_task(
            self.hass,
            self._async_fetch_operation_log(mac, connection),
            name=f"{DOMAIN}.advertised_operation_log.{mac}",
        )

    @callback
    def _async_schedule_log_retry(self, mac: str) -> None:
        """
        Come back to `mac` on a timer while it still owes us records.

        A read that did not reach the lock leaves the flag up, and the
        lock keeps advertising the very same bytes — which HA's
        bluetooth manager does not forward a second time. Waiting for
        another advertisement to retry therefore waits forever; the
        timer is the only thing that gets us back.
        """
        self._async_cancel_log_retry(mac)
        self._log_retries[mac] = async_call_later(
            self.hass,
            LOG_RETRY_COOLDOWN_SECONDS,
            partial(self._async_retry_log, mac),
        )

    @callback
    def _async_cancel_log_retry(self, mac: str) -> None:
        """Drop any pending retry timer for `mac`."""
        cancel = self._log_retries.pop(mac, None)
        if cancel is not None:
            cancel()

    @callback
    def _async_retry_log(self, mac: str, _now: datetime) -> None:
        """
        Come back to a lock that still owes us records.

        No flag re-check here: an advertisement that clears it cancels
        this timer synchronously, so reaching this point means the
        records are still outstanding.
        """
        self._log_retries.pop(mac, None)
        self._async_read_log_if_due(mac)

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
        else:
            # Only once the read landed: it is proof of a live session,
            # which is the whole reason the clock check rides here. A
            # failure above must not reach the retry bookkeeping below
            # as if the log itself had failed.
            await self._async_align_clock(connection)
        finally:
            self._log_fetches.discard(mac)
            if self._records_pending.get(mac, False):
                self._async_schedule_log_retry(mac)

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
        await self._async_describe(connection)
        await self._async_align_clock(connection)
        return {
            "locked": _parse_lock_state(raw_state),
            "battery_level": battery,
        }

    async def _async_describe(self, connection: TtlockBleConnection) -> None:
        """
        Read the lock's hardware strings once per run, on an open session.

        Model, hardware and firmware are static, and each costs a BLE
        round trip, so this rides on a poll that just reached the lock
        instead of connecting for them. Once per Home Assistant run
        rather than once ever: a firmware upgrade changes what the lock
        answers, and a value stored forever would outlive the truth.
        """
        mac = connection.key.lockMac
        if mac in self._described:
            return
        info = await connection.async_get_device_info()
        if info is None:
            return
        self._described.add(mac)
        description: TtlockBleDeviceDescription = {
            "model": info.model,
            "hardware_version": info.hardware_revision,
            "firmware_version": info.firmware_revision,
        }
        if description == self._descriptions.get(mac):
            return
        self._descriptions.async_remember(mac, description)
        self._async_apply_description(mac, description)

    async def _async_align_clock(self, connection: TtlockBleConnection) -> None:
        """
        Compare the lock's clock against local time, and correct a drifted one.

        Rides on a session another read just opened, like the hardware
        description does, and runs at most once a day per lock: the
        answer moves by seconds a day, and a lock only grants a session
        while it is awake.

        The comparison is what makes the lock's operation-log records
        trustworthy. Every record is stamped from this clock, with no
        offset attached, and Home Assistant reads those stamps as local
        time - so a lock whose clock has wandered files the door events
        of a whole day at the wrong hour.
        """
        mac = connection.key.lockMac
        if not self._async_clock_check_due(mac):
            return
        before = dt_util.now()
        lock_time = await connection.async_get_lock_time()
        if lock_time is None:
            return
        # The reference is the midpoint of the read, not its start: the
        # round trip takes seconds over BLE, and charging all of that to
        # the lock would report a healthy clock as drifted.
        reference = before + (dt_util.now() - before) / 2
        drift = (lock_time - reference.replace(tzinfo=None)).total_seconds()
        LOGGER.debug("Clock drift for %s: %+.1fs", mac, drift)
        self._clock_syncs.async_remember(
            mac,
            {"checked_at": dt_util.utcnow().isoformat(), "drift_seconds": drift},
        )
        self.async_update_listeners()
        if abs(drift) <= CLOCK_DRIFT_THRESHOLD_SECONDS:
            return
        await self._async_correct_clock(connection, drift)

    async def _async_correct_clock(
        self,
        connection: TtlockBleConnection,
        drift: float,
    ) -> None:
        """
        Write local time back to a lock whose clock has wandered.

        The reference is taken here rather than reused from the
        comparison: that one is already a round trip old by now, and
        writing it would put the lock behind by exactly the delay the
        check was measuring.

        Only a key carrying an admin password can do this - the firmware
        gates the write behind CHECK_ADMIN. A lock read through a key
        without one still gets its drift reported; there is just nothing
        this integration can do about it.
        """
        mac = connection.key.lockMac
        if not connection.key.adminPs.isdigit():
            LOGGER.debug(
                "Clock of %s is %+.1fs off, but its key carries no admin password",
                mac,
                drift,
            )
            return
        if abs(drift) > CLOCK_LARGE_CORRECTION_SECONDS:
            LOGGER.info(
                "Clock of %s was %+.1fs off local time, correcting it",
                mac,
                drift,
            )
        if not await connection.async_calibrate_time(
            dt_util.now().replace(tzinfo=None)
        ):
            LOGGER.debug("Clock correction did not reach %s", mac)

    def _async_clock_check_due(self, mac: str) -> bool:
        """Report whether `mac` is due for a clock comparison."""
        last = self._clock_syncs.get(mac)
        if last is None:
            return True
        checked_at = dt_util.parse_datetime(last["checked_at"])
        if checked_at is None:
            return True
        age = (dt_util.utcnow() - checked_at).total_seconds()
        return age >= CLOCK_CHECK_INTERVAL_SECONDS

    @callback
    def _async_apply_description(
        self,
        mac: str,
        description: TtlockBleDeviceDescription,
    ) -> None:
        """
        Stamp the hardware strings onto the registry device for `mac`.

        The entity's `device_info` is only read when the entity is
        registered, so a description learned mid-run would otherwise
        wait for the next restart to show up. A field the lock did not
        answer is left untouched rather than blanked - the protocol
        version the entity falls back to is worth more than an empty
        model.
        """
        device_registry = async_get_device_registry(self.hass)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, format_mac(mac))},
        )
        if device is None:
            return
        device_registry.async_update_device(
            device.id,
            model=description["model"] or UNDEFINED,
            hw_version=description["hardware_version"] or UNDEFINED,
            sw_version=description["firmware_version"] or UNDEFINED,
        )


def _parse_lock_state(raw: int | None) -> bool | None:
    """Translate the SDK's tri-state lock value into HA's `bool | None`."""
    if raw == LOCK_STATE_LOCKED:
        return True
    if raw == LOCK_STATE_UNLOCKED:
        return False
    return None
