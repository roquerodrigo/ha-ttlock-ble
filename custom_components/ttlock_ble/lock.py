"""Lock platform for ttlock_ble."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from homeassistant.components.lock import LockEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from ttlock_ble import TTLockError

from .const import LOGGER
from .entity import TtlockBleEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import VirtualKey

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
    Smart lock backed by an on-demand `TtlockBleConnection`.

    State is reported via `_attr_is_locked`. It is updated:
    - On every coordinator refresh that returned a known lock state.
    - Optimistically the moment `async_lock`/`async_unlock` succeed.

    The post-command settle window (`COMMAND_SETTLE_SECONDS`) discards
    coordinator readings that disagree with the just-commanded state
    during a short window after each command — the lock's BLE state can
    briefly disagree with the mechanical state and we don't want the UI
    to bounce.
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

    @callback
    def _handle_coordinator_update(self) -> None:
        """Adopt the coordinator's freshest known lock state, if any."""
        self._sync_from_coordinator()
        super()._handle_coordinator_update()

    def _sync_from_coordinator(self) -> None:
        """
        Copy `locked` from the coordinator snapshot into `_attr_is_locked`.

        A `None` value (lock unreachable at poll time) leaves the cached
        state untouched. The post-command settle window also suppresses
        conflicting coordinator data so the UI doesn't bounce.
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
        """Send LOCK over an on-demand BLE session."""
        await self._async_run_command("lock")

    async def async_unlock(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Send UNLOCK over an on-demand BLE session."""
        await self._async_run_command("unlock")

    async def _async_run_command(self, action: str) -> None:
        """Dispatch the BLE command and optimistically update local state."""
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
