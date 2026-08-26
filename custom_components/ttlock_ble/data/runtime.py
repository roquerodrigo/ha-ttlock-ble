"""State stored on `entry.runtime_data` for the TTLock BLE integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import CALLBACK_TYPE

    from ttlock_ble import VirtualKey

    from ..connection import TtlockBleConnection
    from ..coordinator import TtlockBleDataUpdateCoordinator
    from .stored_key import TtlockBleStoredKey


@dataclass
class TtlockBleData:
    """State stored on `entry.runtime_data` for the TTLock BLE integration."""

    keys: list[TtlockBleStoredKey]
    virtual_keys: list[VirtualKey]
    connections: dict[str, TtlockBleConnection]
    coordinator: TtlockBleDataUpdateCoordinator
    bluetooth_unsubs: list[CALLBACK_TYPE]
