"""
Event platform for ttlock_ble.

Surfaces unsolicited BLE push notifications from the lock (keypad,
fingerprint, IC card, mechanical key, official app) as HA events. The
listener is registered during each coordinator poll, so events arrive
only while the coordinator holds a BLE connection — a full-coverage
push pipeline (always-on connection) is a future iteration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.event import EventEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .connection import event_signal
from .entity import TtlockBleEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import LockEvent, VirtualKey

    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry


EVENT_TYPE_SUCCESS = "operation_success"
EVENT_TYPE_FAILED = "operation_failed"
LOCK_EVENT_STATUS_SUCCESS = 1


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one operation-event entity per `VirtualKey`."""
    data = entry.runtime_data
    async_add_entities(
        TtlockBleOperationEvent(data.coordinator, key) for key in data.virtual_keys
    )


class TtlockBleOperationEvent(TtlockBleEntity, EventEntity):
    """Fires when the lock pushes an unsolicited operation notification."""

    _attr_translation_key = "operation"

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
    ) -> None:
        """Bind the entity to its key + coordinator."""
        super().__init__(coordinator, key)
        self._attr_unique_id = f"{key.lockMac}_operation"
        self._attr_event_types = [EVENT_TYPE_SUCCESS, EVENT_TYPE_FAILED]

    async def async_added_to_hass(self) -> None:
        """Subscribe to the dispatcher signal driven by the coordinator's poll."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                event_signal(self._key.lockMac),
                self._on_lock_event,
            ),
        )

    @callback
    def _on_lock_event(self, event: LockEvent) -> None:
        """
        Translate a `LockEvent` push into an HA event fire.

        Fields the SDK decoded (battery, lock_state, uid, record_id,
        timestamp) become event attributes; consumers can drive
        automations off them directly. Raw `cmd_echo` and `data` hex
        stay attached so an automation can still inspect any opcode the
        SDK doesn't yet recognise.
        """
        event_type = (
            EVENT_TYPE_SUCCESS
            if event.status == LOCK_EVENT_STATUS_SUCCESS
            else EVENT_TYPE_FAILED
        )
        attributes: dict[str, object] = {
            "cmd_echo": event.cmd_echo,
            "data": event.data.hex(),
        }
        if event.battery is not None:
            attributes["battery"] = event.battery
        if event.lock_state is not None:
            attributes["lock_state"] = "unlocked" if event.lock_state == 1 else "locked"
        if event.uid is not None:
            attributes["uid"] = event.uid
        if event.record_id is not None:
            attributes["record_id"] = event.record_id
        if event.timestamp is not None:
            attributes["timestamp"] = event.timestamp
        self._trigger_event(event_type, attributes)
        self.async_write_ha_state()
