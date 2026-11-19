"""TtlockBlePassageModeEntity — an entity worked out from the passage mode slots."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

from .entity import TtlockBleEntity
from .passage_mode import next_transition

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.core import CALLBACK_TYPE

    from ttlock_ble import PassageModeSlot


class TtlockBlePassageModeEntity(TtlockBleEntity):
    """
    Base of the entities whose value follows where the lock's slots stand.

    The lock applies its slots against its own clock and announces nothing
    when one starts or ends, so an entity that shows where the lock stands
    has to work it out. It arms one timer for the next moment any slot
    starts or ends and re-arms it when the slots change, instead of
    re-evaluating on a fixed beat: between two transitions nothing about
    its value moves, so nothing is written.
    """

    _transition: CALLBACK_TYPE | None = None

    @property
    def _slots(self) -> list[PassageModeSlot] | None:
        """Return the slots the lock last listed, `None` until it has."""
        return self.coordinator.async_passage_slots(self._key.lockMac)

    async def async_added_to_hass(self) -> None:
        """Arm the first timer, and drop it when the entity goes."""
        await super().async_added_to_hass()
        self.async_on_remove(self._async_cancel_transition)
        self._async_arm_transition()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Re-arm the timer, as the slots may have changed."""
        self._async_arm_transition()
        super()._handle_coordinator_update()

    @callback
    def _async_arm_transition(self) -> None:
        """Arm the timer for the next moment any slot starts or ends."""
        self._async_cancel_transition()
        slots = self._slots
        if not slots:
            return
        when = next_transition(slots, dt_util.now())
        if when is not None:
            self._transition = async_track_point_in_time(
                self.hass,
                self._async_on_transition,
                when,
            )

    @callback
    def _async_cancel_transition(self) -> None:
        """Drop the timer, if one is armed."""
        if self._transition is not None:
            self._transition()
            self._transition = None

    @callback
    def _async_on_transition(self, _now: datetime) -> None:
        """Publish the new value and arm the timer for the transition after."""
        self._transition = None
        self._async_arm_transition()
        self.async_write_ha_state()
