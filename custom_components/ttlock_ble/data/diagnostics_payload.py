"""Top-level shape returned by `async_get_config_entry_diagnostics`."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .diagnostics_entry import TtlockBleDiagnosticsEntry
    from .diagnostics_lock_summary import TtlockBleDiagnosticsLockSummary
    from .lock_state import TtlockBleLockState


class TtlockBleDiagnosticsPayload(TypedDict):
    """Top-level shape returned by `async_get_config_entry_diagnostics`."""

    entry: TtlockBleDiagnosticsEntry
    locks: list[TtlockBleDiagnosticsLockSummary]
    coordinator_state: Mapping[str, TtlockBleLockState]
