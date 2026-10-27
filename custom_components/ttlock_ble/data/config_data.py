"""Shape of the credentials and key cache persisted on the config entry."""

from __future__ import annotations

from typing import TYPE_CHECKING, NotRequired, TypedDict

if TYPE_CHECKING:
    from .stored_key import TtlockBleStoredKey


class TtlockBleConfigData(TypedDict):
    """
    Shape of the credentials and key cache persisted on the config entry.

    `username`/`password` are absent on entries created from a manually
    entered key: there is no cloud account behind those, so there is
    nothing to re-authenticate against either. `cloud_app` is absent on
    those and on cloud entries created before it existed, which all
    belong to the default app.
    """

    username: NotRequired[str]
    password: NotRequired[str]
    cloud_app: NotRequired[str]
    keys: list[TtlockBleStoredKey]
