"""Build a `VirtualKey` from the manual key form, for locks with no cloud account."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from homeassistant.components.bluetooth import async_last_service_info

from ttlock_ble import LockVersion, VirtualKey

from .advertisement import decode_lock_advertisement
from .const import LOGGER

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ttlock_ble import LockAdvertisement

    from .data import TtlockBleManualKeyInput, TtlockBleStoredKey

_MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")
_AES_KEY_BYTES = 16
_AES_SEPARATORS = (",", ".", " ", "-")


class TtlockBleManualKey:
    """
    Validate the manual key form and turn it into a `VirtualKey`.

    A lock initialised outside the TTLock cloud — by a local BLE bridge,
    for instance — leaves its owner holding exactly what Bluetooth needs
    (the AES key, the unlock key, the admin passcode) and no account to
    download it from. This is the path for those locks.

    Only a handful of the cloud's fields ever reach the wire, so only
    those are asked for. The rest of `VirtualKey` is padding the BLE
    layer never reads: `CHECK_USER_TIME` is sent with a zeroed uid and
    lock-flag position and the firmware's "permanent key" date literals,
    whatever the cloud happened to say.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Bind to the HA instance whose bluetooth manager is cross-checked."""
        self._hass = hass

    def async_validate(self, user_input: TtlockBleManualKeyInput) -> dict[str, str]:
        """Return per-field errors for the form, empty when the input is usable."""
        errors: dict[str, str] = {}
        if not _MAC_PATTERN.match(user_input["lock_mac"].strip()):
            errors["lock_mac"] = "invalid_mac"
        if _aes_key_bytes(user_input["aes_key"]) is None:
            errors["aes_key"] = "invalid_aes_key"
        if not user_input["unlock_key"].strip().isdigit():
            errors["unlock_key"] = "invalid_unlock_key"
        admin_passcode = (user_input.get("admin_passcode") or "").strip()
        if admin_passcode and not admin_passcode.isdigit():
            errors["admin_passcode"] = "invalid_admin_passcode"
        if "lock_mac" not in errors:
            errors.update(self._async_check_against_advertisement(user_input))
        return errors

    def build(self, user_input: TtlockBleManualKeyInput) -> VirtualKey:
        """
        Assemble the `VirtualKey` a validated form describes.

        The AES key is stored as continuous hex rather than however it
        was pasted: the form accepts more separators than the BLE layer
        parses, and a key it cannot read would only fail at the first
        connection, long after the entry looked healthy.
        """
        mac = _normalized_mac(user_input["lock_mac"])
        name = (user_input.get("lock_name") or "").strip() or f"TTLock {mac}"
        aes_key = _aes_key_bytes(user_input["aes_key"])
        if aes_key is None:
            msg = "build() requires input that async_validate accepted"
            raise ValueError(msg)
        return VirtualKey(
            keyId=0,
            lockId=0,
            lockMac=mac,
            lockAlias=name,
            lockName=name,
            lockVersion=LockVersion(
                protocolType=int(user_input["protocol_type"]),
                protocolVersion=int(user_input["protocol_version"]),
                scene=int(user_input["scene"]),
                groupId=int(user_input["group_id"]),
                orgId=int(user_input["org_id"]),
            ),
            aesKeyStr=aes_key.hex(),
            unlockKey=user_input["unlock_key"].strip(),
            lockFlagPos=0,
            timezoneRawOffSet=0,
            adminPs=(user_input.get("admin_passcode") or "").strip(),
        )

    @staticmethod
    def defaults_from(stored_key: TtlockBleStoredKey) -> TtlockBleManualKeyInput:
        """Project a stored key back onto the form, for reconfiguring one."""
        return {
            "lock_mac": stored_key["lockMac"],
            "aes_key": stored_key["aesKeyStr"],
            "unlock_key": stored_key["unlockKey"],
            "admin_passcode": stored_key["adminPs"],
            "lock_name": stored_key["lockAlias"],
            "protocol_type": stored_key["lockVersion"]["protocolType"],
            "protocol_version": stored_key["lockVersion"]["protocolVersion"],
            "scene": stored_key["lockVersion"]["scene"],
            "group_id": stored_key["lockVersion"]["groupId"],
            "org_id": stored_key["lockVersion"]["orgId"],
        }

    def _async_check_against_advertisement(
        self,
        user_input: TtlockBleManualKeyInput,
    ) -> dict[str, str]:
        """
        Compare the entered frame header against what the lock advertises.

        The lock broadcasts its own protocol type, version and scene, so
        when it is in range those three can be checked before the entry
        is created rather than failing later as a lock that never
        answers. Silent when the lock has not been seen — being out of
        range is not an error.
        """
        advertised = self._async_advertised(_normalized_mac(user_input["lock_mac"]))
        if advertised is None:
            return {}
        entered = (
            int(user_input["protocol_type"]),
            int(user_input["protocol_version"]),
            int(user_input["scene"]),
        )
        broadcast = (
            advertised.protocol_type,
            advertised.protocol_version,
            advertised.scene,
        )
        if entered == broadcast:
            return {}
        LOGGER.warning(
            "Manual key for %s declares protocol %d.%d scene %d, "
            "but the lock advertises %d.%d scene %d",
            user_input["lock_mac"],
            *entered,
            *broadcast,
        )
        return {"base": "protocol_mismatch"}

    def _async_advertised(self, mac: str) -> LockAdvertisement | None:
        """Decode the last advertisement seen for `mac`, if any."""
        service_info = async_last_service_info(self._hass, mac, connectable=False)
        if service_info is None:
            return None
        return decode_lock_advertisement(mac, service_info.manufacturer_data)


def _normalized_mac(raw: str) -> str:
    """
    Return `raw` in the uppercase-colon form the rest of the stack uses.

    `async_last_service_info` is an exact lookup keyed by bleak's own
    spelling, so a MAC pasted the way `bluetoothctl` prints it — or with
    dashes, which the form's pattern accepts — silently found nothing
    and skipped the advertisement cross-check entirely, letting through
    exactly the typo that check exists to catch.
    """
    return raw.strip().replace("-", ":").upper()


def _aes_key_bytes(raw: str) -> bytes | None:
    """
    Parse the AES key the way the BLE layer will, or `None` if it cannot.

    Mirrors the library's own accepted forms — separated or continuous
    hex — so a key is rejected in the form rather than at the first
    connection attempt.
    """
    text = raw.strip()
    for separator in _AES_SEPARATORS:
        text = text.replace(separator, "")
    if len(text) != _AES_KEY_BYTES * 2:
        return None
    try:
        return bytes.fromhex(text)
    except ValueError:
        return None
