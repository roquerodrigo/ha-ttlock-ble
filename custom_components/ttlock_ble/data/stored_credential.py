"""How one credential is written to storage."""

from __future__ import annotations

from typing import TypedDict


class TtlockBleStoredCredential(TypedDict):
    """The label a credential is shown with, and the name the user gave it."""

    label: str
    name: str
