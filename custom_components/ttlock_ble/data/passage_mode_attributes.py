"""State attributes of the passage mode binary sensor."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from .passage_slot_description import TtlockBlePassageSlotDescription


class TtlockBlePassageModeAttributes(TypedDict):
    """The passage mode slots the lock was last known to hold."""

    slots: list[TtlockBlePassageSlotDescription]
