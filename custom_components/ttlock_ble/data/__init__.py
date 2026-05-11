"""
Typed shapes and runtime state for the TTLock BLE integration.

One class per file, re-exported here for convenience. `type` aliases that
compose those classes also live here — aliases are not classes and don't
need a separate file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .config_data import TtlockBleConfigData
from .credentials_input import TtlockBleCredentialsInput
from .diagnostics_entry import TtlockBleDiagnosticsEntry
from .diagnostics_lock_summary import TtlockBleDiagnosticsLockSummary
from .diagnostics_payload import TtlockBleDiagnosticsPayload
from .lock_state import TtlockBleLockState
from .options_data import TtlockBleOptionsData
from .runtime import TtlockBleData
from .stored_key import TtlockBleStoredKey
from .stored_lock_version import TtlockBleStoredLockVersion
from .verification_input import TtlockBleVerificationInput

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


type TtlockBleConfigEntry = ConfigEntry[TtlockBleData]
type TtlockBleCoordinatorData = dict[str, TtlockBleLockState]


__all__ = [
    "TtlockBleConfigData",
    "TtlockBleConfigEntry",
    "TtlockBleCoordinatorData",
    "TtlockBleCredentialsInput",
    "TtlockBleData",
    "TtlockBleDiagnosticsEntry",
    "TtlockBleDiagnosticsLockSummary",
    "TtlockBleDiagnosticsPayload",
    "TtlockBleLockState",
    "TtlockBleOptionsData",
    "TtlockBleStoredKey",
    "TtlockBleStoredLockVersion",
    "TtlockBleVerificationInput",
]
