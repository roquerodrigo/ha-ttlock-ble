"""Lock platform for ttlock_ble."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from homeassistant.components.lock import LockEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_call_later

from ttlock_ble import LockState, TTLockError

from .connection import event_signal
from .const import DOMAIN, LOGGER
from .entity import TtlockBleEntity

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from datetime import datetime

    from homeassistant.core import CALLBACK_TYPE, HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import LockEvent, VirtualKey

    from .connection import TtlockBleConnection
    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry


# Upper bound on a command's settle window. The window normally ends
# earlier, on the state push the lock sends once the bolt has stopped
# (about 8 s after the command returns on a DLock-XP V3); this only
# applies when that push never arrives.
COMMAND_SETTLE_SECONDS = 15.0

# How long to wait after a command before reading the operation log. The
# lock writes the record for the command it just executed a moment after
# answering, so an immediate read would miss it.
LOG_FETCH_DELAY_SECONDS = 5.0


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one lock entity per known `VirtualKey`."""
    data = entry.runtime_data
    async_add_entities(
        TtlockBleLock(data.coordinator, key, data.connections[key.lockMac])
        for key in data.virtual_keys
    )


class TtlockBleLock(TtlockBleEntity, LockEntity):
    """
    Smart lock backed by a persistent `TtlockBleConnection`.

    While a command is in flight the entity reports the transitional
    states HA defines for the platform — `locking` and `unlocking` —
    covering the BLE session setup, the round trip to the lock and the
    bolt's travel afterwards, which is seconds rather than milliseconds.
    `jammed`, `open` and `opening` are deliberately never reported: the
    firmware exposes no jam signal (only a bolt position and a success/
    failure byte) and has no latch command distinct from unlocking, so any
    value there would be a guess.

    Settled state is reported via `_attr_is_locked`. It is updated:
    - On every coordinator refresh that returned a known lock state —
      which includes the state decoded from the lock's advertisements,
      the only channel that reports an auto-lock.
    - Optimistically the moment `async_lock`/`async_unlock` succeed.
    - On every push event the SDK forwards (keypad, fingerprint,
      auto-lock): the SDK keeps the BLE link alive for a configurable
      window after each command, so those pushes arrive in real time.
    - On a forced re-query triggered by any push event, as a sanity
      check against losing or misreading a notification.

    After a successful command the entity stays on `locking`/`unlocking`
    and discards readings that disagree with the command until the lock
    reports that the bolt has stopped: the 3-byte `0x14` state push, which
    is then adopted whatever it says. `COMMAND_SETTLE_SECONDS` caps the wait
    for a push that never comes, and one forced query resyncs the state.

    A fixed window shorter than the bolt's travel does not work. The lock
    answers `query_state` with the old position until the bolt stops, and
    the motion pushes it sends meanwhile each trigger such a query, so the
    first one to land after a short window flipped the entity back to the
    pre-command state.

    Readings are judged by when they were *observed*, not when they arrive:
    the post-command poll reads the bolt the instant the command returns and
    only publishes after the log, clock and sound reads behind it. A reading
    is also adopted at most once, because listeners are notified for things
    that never touched the bolt (a sound or clock read, a dormant
    advertisement) and re-applying the snapshot on each of those resurrected
    a reading the entity had already superseded.
    """

    _attr_translation_key = "lock"

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
        connection: TtlockBleConnection,
    ) -> None:
        """Bind the entity to its connection + coordinator + key."""
        super().__init__(coordinator, key)
        self._connection = connection
        self._attr_is_locked = None
        self._attr_is_locking = False
        self._attr_is_unlocking = False
        self._settle_until: float = 0.0
        # Observation time of the state currently shown; see `_adopt`.
        self._observed_at: float = float("-inf")
        self._settle_timer: CALLBACK_TYPE | None = None
        self._command_lock = asyncio.Lock()
        self._sync_from_coordinator()

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_lock"

    async def async_added_to_hass(self) -> None:
        """Subscribe to push-event notifications for the lock's MAC."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                event_signal(self._key.lockMac),
                self._on_lock_event,
            ),
        )
        self.async_on_remove(self._async_cancel_settle_timer)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Adopt the coordinator's freshest known lock state, if any."""
        self._sync_from_coordinator()
        super()._handle_coordinator_update()

    @callback
    def _on_lock_event(self, event: LockEvent) -> None:
        """
        Apply lock state directly from a push notification.

        The 3-byte heartbeat push (cmd_echo=0x14) already carries the
        decoded `lock_state` (0 = locked, 1 = unlocked) — adopt it
        without a follow-up query. The 15-byte log-entry variant has
        no `lock_state`; for those (and any unknown opcode that might
        still signify a change) we fall back to a forced re-query.
        """
        LOGGER.debug(
            "Event-driven update for %s (cmd_echo=0x%02x status=%d lock_state=%s)",
            self._key.lockMac,
            event.cmd_echo,
            event.status,
            event.lock_state,
        )
        if event.lock_state is not None:
            # The lock sends this once the bolt has stopped, so it ends a
            # pending settle window and is adopted whatever it says - a
            # bolt that did not reach the commanded position included.
            if self._settle_timer is not None:
                self._async_end_settle()
            self._apply_lock_state(event.lock_state)
            return
        self._async_create_tracked_task(self._async_query_and_apply(), "query_state")

    def _apply_lock_state(self, raw_state: LockState) -> None:
        """Write `raw_state` onto `_attr_is_locked` respecting the settle window."""
        # `==`, not `is`: callers may hand us the plain int the wire carried
        # rather than the enum member, and identity would silently say False.
        if self._adopt(
            locked=raw_state == LockState.LOCKED,
            observed_at=time.monotonic(),
        ):
            self._write_state_if_added()

    def _adopt(self, *, locked: bool, observed_at: float) -> bool:
        """
        Take `locked`, read at `observed_at`, unless something newer is shown.

        Rejects a reading no newer than the state already shown (a
        re-delivered snapshot, or one taken before the last command
        returned), and one that contradicts a command it was observed
        within `COMMAND_SETTLE_SECONDS` of. Returns whether it was taken.
        """
        if observed_at <= self._observed_at:
            return False
        if observed_at < self._settle_until and locked != self._attr_is_locked:
            LOGGER.debug(
                "Suppressing %s flip for %s observed during command settle window",
                "lock" if locked else "unlock",
                self._key.lockMac,
            )
            return False
        self._attr_is_locked = locked
        self._observed_at = observed_at
        return True

    def _sync_from_coordinator(self) -> None:
        """
        Copy `locked` from the coordinator snapshot into `_attr_is_locked`.

        A `None` value (the lock is out of range, or the poll failed)
        leaves the cached state untouched — the entity keeps showing
        whatever was last known. The post-command settle
        window also suppresses conflicting coordinator data: the lock's
        BLE state can briefly disagree with the just-commanded state
        and we don't want the UI to bounce.
        """
        state = self._lock_state
        if state is None:
            return
        locked = state.get("locked")
        if locked is None:
            return
        observed_at = state.get("observed_at")
        self._adopt(
            locked=locked,
            observed_at=time.monotonic() if observed_at is None else observed_at,
        )

    async def async_lock(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Send LOCK over the persistent BLE connection."""
        await self._async_run_command("lock")

    async def async_unlock(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Send UNLOCK over the persistent BLE connection."""
        await self._async_run_command("unlock")

    async def _async_run_command(self, action: str) -> None:
        """
        Dispatch the BLE command, optimistically update state, refresh.

        The transitional state is cleared in `finally`, not on the error
        path: a command can also end in `asyncio.CancelledError` (HA
        cancels the service call when the client that issued it goes
        away mid-round-trip) and `LockEntity.state` ranks `is_locking`
        above `is_locked`, so anything that skips the reset leaves the
        entity claiming a movement that already ended.

        `_command_lock` serializes the bookkeeping, not just the wire:
        HA runs concurrent service calls, and the BLE layer's own lock
        only orders the round trips. Without it the first command to
        finish would clear the flags and publish a settled state while
        the second was still turning the bolt.
        """
        async with self._command_lock:
            self._async_cancel_settle_timer()
            self._set_in_flight(action)
            moving = False
            try:
                if action == "lock":
                    await self._connection.async_lock()
                else:
                    await self._connection.async_unlock()
            except TTLockError as exc:
                LOGGER.warning(
                    "BLE %s failed for %s: %s",
                    action,
                    self._key.lockMac,
                    exc,
                )
                msg = f"Failed to {action} {self._key.lockMac}: {exc}"
                raise HomeAssistantError(msg) from exc
            else:
                self._attr_is_locked = action == "lock"
                self._observed_at = time.monotonic()
                self._settle_until = self._observed_at + COMMAND_SETTLE_SECONDS
                self._settle_timer = async_call_later(
                    self.hass,
                    COMMAND_SETTLE_SECONDS,
                    self._async_settle_timeout,
                )
                moving = True
            finally:
                # The bolt is still travelling after a successful command;
                # `_async_end_settle` clears the transitional state then.
                if not moving:
                    self._clear_in_flight()
                self._write_state_if_added()
        self._async_create_tracked_task(
            self._async_fetch_log_after_command(),
            "fetch_log_after_command",
        )
        await self.coordinator.async_request_refresh()

    def _async_create_tracked_task(
        self,
        coro: Coroutine[None, None, None],
        name: str,
    ) -> None:
        """
        Run `coro` as a task the config entry owns.

        A bare `hass.async_create_task` is not tied to the entry, so it
        survives an unload and goes on talking to a connection that was
        already stopped.
        """
        self.coordinator.config_entry.async_create_task(
            self.hass,
            coro,
            name=f"{DOMAIN}.{name}.{self._key.lockMac}",
        )

    @callback
    def _async_end_settle(self) -> None:
        """Close the settle window now: the bolt has stopped."""
        self._async_cancel_settle_timer()
        self._settle_until = time.monotonic()
        self._clear_in_flight()

    @callback
    def _async_cancel_settle_timer(self) -> None:
        """Drop the settle timeout, if one is armed."""
        if self._settle_timer is not None:
            self._settle_timer()
            self._settle_timer = None

    @callback
    def _async_settle_timeout(self, _now: datetime) -> None:
        """
        Give up waiting for the push that marks the end of the bolt's travel.

        Every reading taken during the window was suppressed, so the
        entity still shows the commanded state on faith; read the lock
        once more instead of leaving it there.
        """
        self._settle_timer = None
        self._async_end_settle()
        self._write_state_if_added()
        self._async_create_tracked_task(self._async_query_and_apply(), "query_state")

    def _set_in_flight(self, action: str) -> None:
        """Publish the transitional state for a command that just started."""
        self._attr_is_locking = action == "lock"
        self._attr_is_unlocking = action != "lock"
        self._write_state_if_added()

    def _clear_in_flight(self) -> None:
        """Drop the transitional state without publishing it on its own."""
        self._attr_is_locking = False
        self._attr_is_unlocking = False

    def _write_state_if_added(self) -> None:
        """Publish state, unless the entity was removed while we were awaiting."""
        if self.hass is not None and self.entity_id is not None:
            self.async_write_ha_state()

    async def _async_fetch_log_after_command(self) -> None:
        """Fetch operation log shortly after a command to capture the new record."""
        await asyncio.sleep(LOG_FETCH_DELAY_SECONDS)
        await self._connection.async_get_operation_log()

    async def _async_query_and_apply(self) -> None:
        """Force-query state and apply it to `_attr_is_locked` if known."""
        result = await self._connection.async_query_state()
        if result is None:
            LOGGER.debug(
                "Forced query for %s returned no state",
                self._key.lockMac,
            )
            return
        raw_state, _battery = result
        if raw_state is not None:
            self._apply_lock_state(raw_state)
