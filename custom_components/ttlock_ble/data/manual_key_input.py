"""Shape of the manual key form, for locks initialised outside the TTLock cloud."""

from __future__ import annotations

from typing import NotRequired, TypedDict


class TtlockBleManualKeyInput(TypedDict):
    """
    Shape of the manual key form, for locks initialised outside the TTLock cloud.

    The five protocol integers are the frame header the firmware expects
    (`protocol_type`, `protocol_version`, `scene`, `group_id`, `org_id`);
    a lock rejects frames addressed with the wrong ones. `unlock_key` and
    `admin_passcode` are taken verbatim — unlike the cloud payload, which
    delivers them obfuscated.
    """

    lock_mac: str
    aes_key: str
    unlock_key: str
    admin_passcode: NotRequired[str]
    lock_name: NotRequired[str]
    protocol_type: int
    protocol_version: int
    scene: int
    group_id: int
    org_id: int
