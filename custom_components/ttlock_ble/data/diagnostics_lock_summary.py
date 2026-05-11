"""Per-lock summary in the diagnostics dump (without secrets)."""

from __future__ import annotations

from typing import TypedDict


class TtlockBleDiagnosticsLockSummary(TypedDict):
    """Per-lock summary in the diagnostics dump (without secrets)."""

    lockId: int
    lockMac: str
    lockAlias: str
    lockName: str
    keyType: int
    userType: str
