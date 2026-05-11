"""Lock-version triple persisted alongside a stored key."""

from __future__ import annotations

from typing import TypedDict


class TtlockBleStoredLockVersion(TypedDict):
    """Lock-version triple persisted alongside a stored key."""

    protocolType: int
    protocolVersion: int
    scene: int
    groupId: int
    orgId: int
