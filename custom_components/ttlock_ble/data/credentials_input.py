"""User-supplied credentials before the cloud round-trip."""

from __future__ import annotations

from typing import TypedDict


class TtlockBleCredentialsInput(TypedDict):
    """User-supplied credentials before the cloud round-trip."""

    username: str
    password: str
