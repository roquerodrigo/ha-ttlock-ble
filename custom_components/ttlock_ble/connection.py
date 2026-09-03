"""
Persistent BLE connection wrapper for ttlock_ble.

Each `TtlockBleConnection` owns a long-lived `TTLockClient` for a single
`VirtualKey`, runs a background reconnect loop, and serializes state
queries and lock commands through a single `asyncio.Lock`. Push events
arriving on that connection are dispatched live via HA's dispatcher
under the signal `ttlock_ble_event_<mac>`.

The reconnect loop waits on an `asyncio.Event` that the SDK's
`disconnected_callback` toggles, so the watchdog wakes up the instant
the BLE link drops instead of poll-sleeping.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
from typing import TYPE_CHECKING

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from ttlock_ble import TTLockClient, TTLockError

from .const import DOMAIN, LOGGER
from .credentials import (
    async_client_get_fingerprints,
    async_client_get_ic_cards,
    async_client_get_passcodes,
)
from .data import TtlockBleLogCursor
from .passage import (
    async_client_clear_passage_mode,
    async_client_delete_passage_mode,
    async_client_get_passage_mode,
    async_client_set_passage_mode,
)

if TYPE_CHECKING:
    from datetime import datetime

    from bleak import BleakClient
    from homeassistant.core import HomeAssistant

    from ttlock_ble import DeviceInfo, LockEvent, LockState, LogEntry, VirtualKey

    from .data import TtlockBlePassageSchedule


RECONNECT_INITIAL_BACKOFF = 1.0
RECONNECT_MAX_BACKOFF = 300.0

# The lock answers the operation log one record per BLE frame, each with
# its own timeout, and the SDK holds its command lock for the whole
# pagination. Unbounded, a lock with a long unsynced history makes the
# first fetch of a session sit in front of a user pressing Unlock for
# tens of seconds. Anything older than this batch is picked up by the
# next poll.
MAX_LOG_ENTRIES_PER_FETCH = 25


def event_signal(mac: str) -> str:
    """Dispatcher signal that carries `LockEvent`s for `mac`."""
    return f"{DOMAIN}_event_{mac.lower()}"


def log_signal(mac: str) -> str:
    """Dispatcher signal that carries `LogEntry` records for `mac`."""
    return f"{DOMAIN}_log_{mac.lower()}"


def connection_signal(mac: str) -> str:
    """Dispatcher signal that carries BLE up/down transitions for `mac`."""
    return f"{DOMAIN}_connection_{mac.lower()}"


def auto_lock_signal(mac: str) -> str:
    """Dispatcher signal that carries auto-lock delay changes for `mac`."""
    return f"{DOMAIN}_auto_lock_{mac.lower()}"


def passage_mode_signal(mac: str) -> str:
    """Dispatcher signal that carries passage mode state changes for `mac`."""
    return f"{DOMAIN}_passage_mode_{mac.lower()}"


def credentials_count_signal(mac: str) -> str:
    """Dispatcher signal that carries credential count changes for `mac`."""
    return f"{DOMAIN}_credentials_count_{mac.lower()}"


class TtlockBleConnection:
    """Maintain a long-lived BLE session with one TTLock lock."""

    def __init__(
        self,
        hass: HomeAssistant,
        key: VirtualKey,
        log_cursor: TtlockBleLogCursor | None = None,
    ) -> None:
        """
        Bind to the HA instance and the credentials for a single lock.

        Nothing connects until someone asks. `async_start` is what opens
        a session and keeps reopening it, and it is only called for an
        entry that turned the permanent connection on.

        `log_cursor` restores where the operation log was last read, so
        the backlog pass below is not repeated after a restart and new
        records are dispatched straight away.
        """
        self._hass = hass
        self._key = key
        self._client: TTLockClient | None = None
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._closing = False
        self._disconnected = asyncio.Event()
        cursor = log_cursor or TtlockBleLogCursor()
        self._seen_records: set[int] = set(cursor.records)
        self._log_seeded = cursor.seeded
        self._on_records_seen = cursor.on_move
        self._broadcast_connected = False
        self._auto_lock_seconds: int | None = None
        self._auto_lock_limits: tuple[int | None, int | None] = (None, None)
        self._last_active_auto_lock: int = 10
        self._passage_mode_active: bool | None = None
        self._passage_schedules: list[TtlockBlePassageSchedule] = []
        self._credentials_counts: dict[str, int | None] = {
            "passcodes": None,
            "cards": None,
            "fingerprints": None,
        }

    @property
    def key(self) -> VirtualKey:
        """Return the `VirtualKey` this connection wraps."""
        return self._key

    @property
    def is_connected(self) -> bool:
        """True iff the underlying `TTLockClient` is currently connected."""
        return self._client is not None and self._client.is_connected

    @property
    def auto_lock_seconds(self) -> int | None:
        """Return the currently cached auto-lock delay in seconds."""
        return self._auto_lock_seconds

    @property
    def auto_lock_limits(self) -> tuple[int | None, int | None]:
        """Return the min/max auto-lock delay supported by hardware."""
        return self._auto_lock_limits

    @property
    def last_active_auto_lock(self) -> int:
        """Return the last active non-zero auto-lock delay."""
        return self._last_active_auto_lock

    @property
    def passage_mode_active(self) -> bool | None:
        """Return whether passage mode is currently known to be enabled."""
        return self._passage_mode_active

    @property
    def passage_schedules(self) -> list[TtlockBlePassageSchedule]:
        """Return cached passage mode schedule slots."""
        return self._passage_schedules

    def get_credential_count(self, cred_type: str) -> int | None:
        """Return cached count for a credential type."""
        return self._credentials_counts.get(cred_type)

    def set_credential_count(self, cred_type: str, count: int) -> None:
        """Update cached count for a credential type and notify listeners."""
        self._credentials_counts[cred_type] = count
        async_dispatcher_send(
            self._hass,
            credentials_count_signal(self._key.lockMac),
            cred_type,
            count,
        )

    async def async_fetch_credentials_count(self, cred_type: str) -> int | None:
        """Fetch credentials of given type over BLE and update count."""
        if cred_type == "passcodes":
            creds = await self.async_get_passcodes()
        elif cred_type == "cards":
            creds = await self.async_get_cards()
        elif cred_type == "fingerprints":
            creds = await self.async_get_fingerprints()
        else:
            return None
        return len(creds)

    async def async_start(self) -> None:
        """
        Hold a BLE session open, reopening it whenever it drops.

        Only started for an entry with the permanent connection on. It
        buys instant commands and live push events, and it costs the
        lock's battery: the firmware drops an idle session within
        seconds, so this reconnects about as often.
        """
        if self._task is not None:
            return
        self._closing = False
        self._task = self._hass.async_create_background_task(
            self._async_maintain(),
            name=f"ttlock_ble.connection.{self._key.lockMac}",
        )

    async def async_stop(self) -> None:
        """Cancel the background loop and release the BLE connection."""
        self._closing = True
        self._disconnected.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        async with self._lock:
            await self._async_disconnect_locked()

    async def async_query_state(self) -> tuple[LockState | None, int | None] | None:
        """
        Return `(lock_state, battery)` through the live connection.

        Returns `None` when the lock is out of range or the query failed.
        Every caller is already rate-limited — the coordinator by
        `scan_interval`, the lock entity by the user pressing a button —
        so the reconnect cooldown the maintain loop keeps is deliberately
        not consulted here: it paces the background loop, not the reads.
        """
        async with self._lock:
            client = await self._async_ensure_connected_locked()
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
                await self._async_disconnect_locked()
                return None

    async def async_get_device_info(self) -> DeviceInfo | None:
        """
        Read the lock's Device Information Service through the connection.

        Returns `None` when the lock is out of range or the read failed.
        These are plain Bluetooth SIG characteristics rather than the
        lock's own protocol, so nothing here is encrypted and no
        handshake is involved - but they still need a session, and the
        lock only grants one while it is awake.
        """
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                return None
            try:
                return await client.get_device_info()
            except Exception as exc:  # noqa: BLE001
                # The SDK reports an unreadable characteristic as `None`
                # rather than raising, so anything arriving here broke
                # the link itself. Hardware strings are not worth losing
                # a poll over: the caller keeps whatever it knew.
                LOGGER.debug(
                    "get_device_info failed for %s: %s",
                    self._key.lockMac,
                    exc,
                )
                return None

    async def async_get_lock_time(self) -> datetime | None:
        """
        Read the lock's own clock through the connection.

        Returns `None` when the lock is out of range or the read failed.
        The value is naive and carries no offset: it is whatever wall
        clock was last written to the lock, which for a lock set up by
        the official app is local time.

        No admin handshake is involved - the firmware answers this one
        unauthenticated, unlike `async_calibrate_time`.
        """
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                return None
            try:
                return await client.get_lock_time()
            except Exception as exc:  # noqa: BLE001
                # A clock reading is not worth losing a poll over: the
                # caller keeps whatever it knew and tries again later.
                LOGGER.debug(
                    "get_lock_time failed for %s: %s",
                    self._key.lockMac,
                    exc,
                )
                return None

    async def async_calibrate_time(self, local_time: datetime) -> bool:
        """
        Write `local_time` to the lock's clock. Reports whether it landed.

        `local_time` is stored verbatim, with no offset attached, and is
        what the lock reports back in every operation-log record - so it
        has to be the wall clock the records are meant to read in, not
        UTC.

        Admin-gated by the firmware, so a key carrying no admin password
        can only ever fail here; callers check that before asking.
        """
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                return False
            try:
                await client.calibrate_time(local_time)
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug(
                    "calibrate_time failed for %s: %s",
                    self._key.lockMac,
                    exc,
                )
                return False
            return True

    async def async_lock(self) -> None:
        """Send a LOCK command on the live connection (raises on failure)."""
        await self._async_run_command("lock")

    async def async_unlock(self) -> None:
        """Send an UNLOCK command on the live connection (raises on failure)."""
        await self._async_run_command("unlock")

    async def async_set_lock_sound(self, *, enabled: bool) -> None:
        """Turn the lock's beep on or off (raises on failure)."""
        await self._async_run_command("sound_on" if enabled else "sound_off")

    async def async_get_passage_mode(self) -> list[TtlockBlePassageSchedule]:
        """Fetch all passage mode schedule slots from the lock."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                raise TTLockError(f"Lock {self._key.lockMac} is not reachable")
            schedules = await async_client_get_passage_mode(client)
            self._passage_schedules = schedules
            self._passage_mode_active = bool(schedules)
            async_dispatcher_send(
                self._hass,
                passage_mode_signal(self._key.lockMac),
                schedules,
            )
            return schedules

    async def async_set_passage_mode(
        self,
        schedules: list[TtlockBlePassageSchedule],
        *,
        clear_existing: bool = False,
    ) -> None:
        """Set one or more passage mode schedule slots on the lock."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                raise TTLockError(f"Lock {self._key.lockMac} is not reachable")
            await async_client_set_passage_mode(
                client,
                schedules,
                clear_existing=clear_existing,
            )
            self._passage_schedules = schedules
            self._passage_mode_active = bool(schedules)
            async_dispatcher_send(
                self._hass,
                passage_mode_signal(self._key.lockMac),
                schedules,
            )

    async def async_delete_passage_mode(
        self,
        schedule: TtlockBlePassageSchedule,
    ) -> None:
        """Delete a specific passage mode schedule slot from the lock."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                raise TTLockError(f"Lock {self._key.lockMac} is not reachable")
            await async_client_delete_passage_mode(client, schedule)

    async def async_clear_passage_mode(self) -> None:
        """Clear all passage mode schedule slots from the lock."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                raise TTLockError(f"Lock {self._key.lockMac} is not reachable")
            await async_client_clear_passage_mode(client)
            self._passage_schedules = []
            self._passage_mode_active = False
            async_dispatcher_send(
                self._hass,
                passage_mode_signal(self._key.lockMac),
                [],
            )

    async def async_get_auto_lock_info(self) -> dict[str, Any]:
        """Fetch current auto-lock duration and hardware limits."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                raise TTLockError(f"Lock {self._key.lockMac} is not reachable")
            seconds = await client.get_auto_lock_time()
            min_sec: int | None = None
            max_sec: int | None = None
            try:
                limits = await client.get_auto_lock_limits()
                min_sec = limits.min_allowed
                max_sec = limits.max_allowed
            except Exception:  # noqa: BLE001
                pass
            self._auto_lock_seconds = seconds
            if seconds > 0:
                self._last_active_auto_lock = seconds
            self._auto_lock_limits = (min_sec, max_sec)
            async_dispatcher_send(
                self._hass,
                auto_lock_signal(self._key.lockMac),
                seconds,
            )
            return {
                "auto_lock_seconds": seconds,
                "enabled": seconds > 0,
                "min_seconds": min_sec,
                "max_seconds": max_sec,
            }

    async def async_set_auto_lock_time(self, seconds: int) -> None:
        """Set auto-lock delay in seconds (0 = disabled)."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                raise TTLockError(f"Lock {self._key.lockMac} is not reachable")
            await client.set_auto_lock_time(seconds)
            self._auto_lock_seconds = seconds
            if seconds > 0:
                self._last_active_auto_lock = seconds
            async_dispatcher_send(
                self._hass,
                auto_lock_signal(self._key.lockMac),
                seconds,
            )

    async def async_get_lock_clock(self) -> dict[str, Any]:
        """Read the lock's real-time hardware clock and compute drift."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                raise TTLockError(f"Lock {self._key.lockMac} is not reachable")
            before = dt_util.now()
            lock_time = await client.get_lock_time()
            if lock_time is None:
                raise TTLockError(f"Could not read clock from lock {self._key.lockMac}")
            reference = before + (dt_util.now() - before) / 2
            drift = (lock_time - reference.replace(tzinfo=None)).total_seconds()
            return {
                "lock_time": lock_time.isoformat(),
                "local_time": reference.isoformat(),
                "drift_seconds": round(drift, 1),
            }

    async def async_fetch_operation_log(
        self,
        max_entries: int = 50,
        from_sequence: int | None = None,
        to_sequence: int | None = None,
        start_date: dt.datetime | str | None = None,
        end_date: dt.datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch raw operation log records from the lock for display/inspection."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                raise TTLockError(f"Lock {self._key.lockMac} is not reachable")

            target_start_record: int | None = None
            if from_sequence is not None:
                target_start_record = from_sequence
            elif to_sequence is not None:
                target_start_record = max(0, to_sequence - max_entries + 1)
            elif self._seen_records:
                highest_seen = max(self._seen_records)
                target_start_record = max(0, highest_seen - max_entries + 1)

            if target_start_record is not None:
                seq = target_start_record
            else:
                seq = 0xFFFF

            # If filtering by to_sequence or date, fetch enough entries so filtering does not truncate
            if to_sequence is not None and target_start_record is not None:
                fetch_count = max(max_entries, (to_sequence - target_start_record + 1)) + 5
            elif to_sequence is not None or start_date is not None or end_date is not None:
                fetch_count = max_entries + 50
            else:
                fetch_count = max_entries

            entries = await client.get_operation_log(
                max_entries=fetch_count,
                from_sequence=seq,
            )
            # If default 0xFFFF (unread only) returned nothing, fall back to historical records
            if not entries and target_start_record is None and seq == 0xFFFF:
                entries = await client.get_operation_log(
                    max_entries=fetch_count,
                    from_sequence=0,
                )

            # Update known seen records so highest_seen is kept fresh
            if entries:
                self._seen_records.update(e.record_number for e in entries)

            # Parse filter bounds if provided
            dt_start: dt.datetime | None = None
            if start_date:
                dt_start = (
                    start_date
                    if isinstance(start_date, dt.datetime)
                    else dt_util.parse_datetime(str(start_date))
                )
            dt_end: dt.datetime | None = None
            if end_date:
                dt_end = (
                    end_date
                    if isinstance(end_date, dt.datetime)
                    else dt_util.parse_datetime(str(end_date))
                )

            # Filter entries by sequence range and dates
            filtered: list[LogEntry] = []
            for entry in entries:
                if target_start_record is not None and entry.record_number < target_start_record:
                    continue
                if to_sequence is not None and entry.record_number > to_sequence:
                    continue
                if dt_start is not None or dt_end is not None:
                    if entry.operate_date is None:
                        continue
                    entry_dt = entry.operate_date.replace(tzinfo=None)
                    if dt_start is not None and entry_dt < dt_start.replace(tzinfo=None):
                        continue
                    if dt_end is not None and entry_dt > dt_end.replace(tzinfo=None):
                        continue
                filtered.append(entry)

            # Order newest entries first
            filtered.sort(key=lambda e: e.record_number, reverse=True)
            if max_entries:
                filtered = filtered[:max_entries]

            results: list[dict[str, Any]] = []
            for entry in filtered:
                rec_type = entry.record_type
                rec_type_name = (
                    rec_type.name if hasattr(rec_type, "name") else str(rec_type)
                )
                results.append({
                    "record_number": entry.record_number,
                    "record_type": rec_type_name,
                    "operate_date": (
                        entry.operate_date.isoformat()
                        if entry.operate_date
                        else None
                    ),
                    "lock_battery": entry.lock_battery,
                    "uid": entry.uid,
                    "record_id": entry.record_id,
                    "credential": entry.password,
                    "key_id": entry.key_id,
                })
            return results

    async def async_get_passcodes(self) -> list[dict[str, Any]]:
        """Query all programmed keyboard passcodes from the lock."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                raise TTLockError(f"Lock {self._key.lockMac} is not reachable")
            passcodes = await async_client_get_passcodes(client)
            self.set_credential_count("passcodes", len(passcodes))
            return passcodes

    async def async_get_cards(self) -> list[dict[str, Any]]:
        """Query all enrolled RFID / IC cards from the lock."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                raise TTLockError(f"Lock {self._key.lockMac} is not reachable")
            cards = await async_client_get_ic_cards(client)
            self.set_credential_count("cards", len(cards))
            return cards

    async def async_get_fingerprints(self) -> list[dict[str, Any]]:
        """Query all enrolled biometric fingerprints from the lock."""
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                raise TTLockError(f"Lock {self._key.lockMac} is not reachable")
            fingerprints = await async_client_get_fingerprints(client)
            self.set_credential_count("fingerprints", len(fingerprints))
            return fingerprints

    async def async_get_operation_log(self) -> list[LogEntry]:
        """
        Fetch operation records from the lock and dispatch the new ones.

        On a lock with no restored cursor, the first fetch that actually
        reaches it only seeds `_seen_records` and returns nothing. The
        lock hands back everything unsynced since its last cursor sync,
        and that set is history — replaying it through the event entity
        would fire automations for unlocks that happened days ago.

        That pass runs once per lock, not once per Home Assistant start:
        the cursor is persisted, so a restart resumes where the previous
        run stopped. Tying it to the start instead is what used to make
        a restart swallow whatever happened at the door just after it,
        which is neither history nor something to replay.

        Seeding is tied to a successful fetch, not to an attempt: a lock
        out of range on first setup gets its seeding pass whenever it
        first answers.
        """
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                LOGGER.warning("get_operation_log: no client for %s", self._key.lockMac)
                return []
            try:
                entries = await client.get_operation_log(
                    max_entries=MAX_LOG_ENTRIES_PER_FETCH,
                )
            except Exception as exc:  # noqa: BLE001
                # `TTLockError` alone is not enough: the SDK's log path
                # reaches `aes_decrypt` unwrapped and raises `ValueError`
                # on a garbled frame, and `bleak` raises `BleakError` when
                # the link drops mid-fetch. Letting those out would fail
                # the whole poll and discard the state read that already
                # succeeded, leaving the lock entity reporting a stale
                # value instead of merely losing its history.
                LOGGER.warning(
                    "get_operation_log failed for %s: %s",
                    self._key.lockMac,
                    exc,
                )
                return []
        LOGGER.debug(
            "get_operation_log for %s: %d entries, seen=%d",
            self._key.lockMac,
            len(entries),
            len(self._seen_records),
        )
        new_entries: list[LogEntry] = []
        for entry in entries:
            if entry.record_number not in self._seen_records:
                self._seen_records.add(entry.record_number)
                new_entries.append(entry)
        seeding = not self._log_seeded
        self._log_seeded = True
        if (new_entries or seeding) and self._on_records_seen is not None:
            self._on_records_seen(self._seen_records)
        if seeding:
            LOGGER.debug(
                "Lock %s: seeded %d existing log records, none dispatched",
                self._key.lockMac,
                len(new_entries),
            )
            return []
        if new_entries:
            LOGGER.debug(
                "Lock %s: dispatching %d new log entries",
                self._key.lockMac,
                len(new_entries),
            )
            for entry in new_entries:
                async_dispatcher_send(
                    self._hass,
                    log_signal(self._key.lockMac),
                    entry,
                )
        return new_entries

    async def _async_run_command(self, action: str) -> None:
        """
        Acquire the lock, ensure connected, then run one command on it.

        Everything that is not already a `TTLockError` is converted into
        one so callers only ever see the integration's own exception
        hierarchy. That is not belt-and-suspenders: the SDK's command
        path reaches `bleak.write_gatt_char` unwrapped (`BleakError`
        when the link drops mid-command), raises a bare `RuntimeError`
        when the lock rejects `checkUserTime`, and lets `ValueError` out
        of `aes_decrypt` on a garbled frame. `TTLockError` subclasses
        `RuntimeError`, so it has to be caught first.
        """
        async with self._lock:
            client = await self._async_ensure_connected_locked()
            if client is None:
                msg = f"Lock {self._key.lockMac} not reachable via Bluetooth"
                raise TTLockError(msg)
            try:
                if action == "lock":
                    await client.lock()
                elif action == "unlock":
                    await client.unlock()
                else:
                    await client.set_lock_sound(enabled=action == "sound_on")
            except TTLockError:
                await self._async_disconnect_locked()
                raise
            except TimeoutError as exc:
                await self._async_disconnect_locked()
                msg = f"Lock {self._key.lockMac} timed out responding to {action}"
                raise TTLockError(msg) from exc
            except Exception as exc:
                await self._async_disconnect_locked()
                msg = f"Lock {self._key.lockMac} failed to {action}: {exc}"
                raise TTLockError(msg) from exc

    async def _async_ensure_connected_locked(self) -> TTLockClient | None:
        """
        Return a live client, opening a new BLE session if needed.

        Caller must hold `self._lock`. Returns `None` on failure (lock
        not discoverable or BLE connect raised), and once `async_stop`
        has run: a late caller that opened a session then would take the
        lock's single central slot with nobody left to close it, and
        block the connection the reloaded entry is trying to make.
        """
        if self._closing:
            return None
        if self._client is not None and self._client.is_connected:
            return self._client
        await self._async_disconnect_locked()
        device = async_ble_device_from_address(
            self._hass,
            self._key.lockMac,
            connectable=True,
        )
        if device is None:
            return None
        client = TTLockClient.from_ble_device(
            device,
            self._key,
            disconnected_callback=self._on_disconnected,
        )
        try:
            await client.connect()
        except Exception as exc:  # noqa: BLE001
            # `TTLockError` alone is not enough: the SDK's connect path
            # leaves `start_notify` unwrapped, so bleak raises a plain
            # `BleakError` when the link drops between the connect and
            # the subscription. Letting that out bypasses the wrapper
            # every command path relies on, and the user gets an unknown
            # error with a traceback instead of a failure that names the
            # lock. The half-open session is closed here rather than
            # left to the firmware's idle timeout.
            LOGGER.debug("BLE connect failed for %s: %s", self._key.lockMac, exc)
            with contextlib.suppress(Exception):
                await client.disconnect()
            return None
        client.add_event_listener(self._on_event)
        self._client = client
        self._disconnected.clear()
        self._broadcast_connection_state(connected=True)
        return client

    async def _async_disconnect_locked(self) -> None:
        """Tear down the BLE session if up. Caller must hold `self._lock`."""
        if self._client is None:
            return
        client = self._client
        self._client = None
        self._broadcast_connection_state(connected=False)
        client.remove_event_listener(self._on_event)
        with contextlib.suppress(Exception):
            await client.disconnect()

    def _broadcast_connection_state(self, *, connected: bool) -> None:
        """
        Notify subscribers that the BLE link to this lock just changed.

        Repeats are dropped: the down edge is announced the moment bleak
        reports the drop, and the teardown that eventually follows must
        not announce it a second time.
        """
        if connected == self._broadcast_connected:
            return
        self._broadcast_connected = connected
        async_dispatcher_send(
            self._hass,
            connection_signal(self._key.lockMac),
            connected,
        )

    def _on_event(self, event: LockEvent) -> None:
        """Forward a push event onto HA's dispatcher (called by the BLE layer)."""
        async_dispatcher_send(
            self._hass,
            event_signal(self._key.lockMac),
            event,
        )

    def _on_disconnected(self, _client: BleakClient) -> None:
        """
        Wake the maintain loop the moment bleak signals a drop.

        The drop is also announced here rather than from
        `_async_disconnect_locked`: that runs after the reconnect
        cooldown, so the connectivity sensor claimed a live link for
        most of every cooldown cycle.
        """
        self._disconnected.set()
        self._broadcast_connection_state(connected=False)

    async def _async_maintain(self) -> None:
        """
        Background loop that reopens the BLE session as soon as it drops.

        This is the permanent connection, so a drop is followed straight
        away by another connect. The lock drops an idle session within
        seconds, which makes this loop a reconnect storm by design — the
        battery cost is the whole trade the option asks the user to
        accept. Connect failures use exponential backoff, so a lock that
        is not answering is not hammered on top of that.
        """
        backoff = RECONNECT_INITIAL_BACKOFF
        while not self._closing:
            try:
                async with self._lock:
                    client = await self._async_ensure_connected_locked()
                if client is None:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, RECONNECT_MAX_BACKOFF)
                    continue
                backoff = RECONNECT_INITIAL_BACKOFF
                await self._disconnected.wait()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                LOGGER.exception(
                    "Connection maintenance error for %s",
                    self._key.lockMac,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, RECONNECT_MAX_BACKOFF)
