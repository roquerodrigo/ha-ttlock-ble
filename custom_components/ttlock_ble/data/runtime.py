"""State stored on `entry.runtime_data` for the TTLock BLE integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from custom_components.ttlock_ble.connection import TtlockBleConnection
    from custom_components.ttlock_ble.coordinator import (
        TtlockBleDataUpdateCoordinator,
    )
    from ttlock_ble import VirtualKey

    from .stored_key import TtlockBleStoredKey


@dataclass
class TtlockBleData:
    """State stored on `entry.runtime_data` for the TTLock BLE integration."""

    keys: list[TtlockBleStoredKey]
    virtual_keys: list[VirtualKey]
    connections: dict[str, TtlockBleConnection]
    coordinator: TtlockBleDataUpdateCoordinator
