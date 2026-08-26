"""Top-level shape returned by `async_get_config_entry_diagnostics`."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .device_description import TtlockBleDeviceDescription
    from .diagnostics_advertisement import TtlockBleDiagnosticsAdvertisement
    from .diagnostics_entry import TtlockBleDiagnosticsEntry
    from .diagnostics_lock_summary import TtlockBleDiagnosticsLockSummary
    from .lock_state import TtlockBleLockState


class TtlockBleDiagnosticsPayload(TypedDict):
    """Top-level shape returned by `async_get_config_entry_diagnostics`."""

    entry: TtlockBleDiagnosticsEntry
    locks: list[TtlockBleDiagnosticsLockSummary]
    coordinator_state: Mapping[str, TtlockBleLockState]
    advertisements: Mapping[str, TtlockBleDiagnosticsAdvertisement | None]
    device_descriptions: Mapping[str, TtlockBleDeviceDescription | None]
