"""User-supplied credentials before the cloud round-trip."""

from __future__ import annotations

from typing import NotRequired, TypedDict


class TtlockBleCredentialsInput(TypedDict):
    """
    User-supplied credentials before the cloud round-trip.

    `cloud_app` is only asked when an entry is created; reauth and
    reconfigure keep the app the entry already belongs to.
    """

    username: str
    password: str
    cloud_app: NotRequired[str]
