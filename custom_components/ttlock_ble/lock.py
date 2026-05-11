"""Lock platform for ttlock_ble."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from homeassistant.components.lock import LockEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from ttlock_ble import TTLockError

from .connection import event_signal
from .const import LOGGER
from .coordinator import LOCK_STATE_LOCKED, LOCK_STATE_UNLOCKED
from .entity import TtlockBleEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import LockEvent, VirtualKey

    from .connection import TtlockBleConnection
    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry


COMMAND_SETTLE_SECONDS = 4.0


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

    State is reported via `_attr_is_locked`. It is updated:
    - On every coordinator refresh that returned a known lock state.
    - Optimistically the moment `async_lock`/`async_unlock` succeed.
    - On every push event the SDK forwards (keypad, fingerprint,
      auto-lock): the SDK keeps the BLE link alive for a configurable
      window after each command, so those pushes arrive in real time.
    - On a forced re-query triggered by any push event, as a sanity
      check against losing or misreading a notification.

    The post-command settle window (`COMMAND_SETTLE_SECONDS`) discards
    state readings that disagree with the just-commanded state during
    a short window after each command — the lock's BLE state can
    briefly disagree with the mechanical state and we don't want the
    UI to bounce.
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
        self._attr_unique_id = f"{key.lockMac}_lock"
        self._attr_is_locked = None
        self._settle_until: float = 0.0
        self._sync_from_coordinator()

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
        LOGGER.info(
            "Event-driven update for %s (cmd_echo=0x%02x status=%d lock_state=%s)",
            self._key.lockMac,
            event.cmd_echo,
            event.status,
            event.lock_state,
        )
        if event.lock_state is not None:
            self._apply_lock_state(event.lock_state)
            return
        self.hass.async_create_task(self._async_query_and_apply())

    def _apply_lock_state(self, raw_state: int) -> None:
        """Write `raw_state` onto `_attr_is_locked` respecting the settle window."""
        if raw_state == LOCK_STATE_LOCKED:
            new_locked = True
        elif raw_state == LOCK_STATE_UNLOCKED:
            new_locked = False
        else:
            return
        if time.monotonic() < self._settle_until and new_locked != self._attr_is_locked:
            LOGGER.debug(
                "Suppressing %s flip for %s during command settle window",
                "lock" if new_locked else "unlock",
                self._key.lockMac,
            )
            return
        self._attr_is_locked = new_locked
        self.async_write_ha_state()

    def _sync_from_coordinator(self) -> None:
        """
        Copy `locked` from the coordinator snapshot into `_attr_is_locked`.

        A `None` value (cooldown suppressed the poll, or the lock is
        out of range) leaves the cached state untouched — the entity
        keeps showing whatever was last known. The post-command settle
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
        if time.monotonic() < self._settle_until and locked != self._attr_is_locked:
            LOGGER.debug(
                "Suppressing coordinator flip for %s during command settle window",
                self._key.lockMac,
            )
            return
        self._attr_is_locked = locked

    async def async_lock(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Send LOCK over the persistent BLE connection."""
        await self._async_run_command("lock")

    async def async_unlock(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Send UNLOCK over the persistent BLE connection."""
        await self._async_run_command("unlock")

    async def _async_run_command(self, action: str) -> None:
        """Dispatch the BLE command, optimistically update state, refresh."""
        try:
            if action == "lock":
                await self._connection.async_lock()
            else:
                await self._connection.async_unlock()
        except TTLockError as exc:
            LOGGER.warning("BLE %s failed for %s: %s", action, self._key.lockMac, exc)
            msg = f"Failed to {action} {self._key.lockMac}: {exc}"
            raise HomeAssistantError(msg) from exc
        self._attr_is_locked = action == "lock"
        self._settle_until = time.monotonic() + COMMAND_SETTLE_SECONDS
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def _async_query_and_apply(self) -> None:
        """Force-query state and apply it to `_attr_is_locked` if known."""
        result = await self._connection.async_query_state(force_cooldown_bypass=True)
        if result is None:
            LOGGER.debug(
                "Forced query for %s returned no state",
                self._key.lockMac,
            )
            return
        raw_state, _battery = result
        self._apply_lock_state(raw_state)
