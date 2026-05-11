"""Shape of the credentials and key cache persisted on the config entry."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from .stored_key import TtlockBleStoredKey


class TtlockBleConfigData(TypedDict):
    """Shape of the credentials and key cache persisted on the config entry."""

    username: str
    password: str
    keys: list[TtlockBleStoredKey]
