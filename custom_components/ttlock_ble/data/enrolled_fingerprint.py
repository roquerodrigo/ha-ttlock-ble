"""Identity of one fingerprint enrolled on a lock."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from ttlock_ble import FingerprintEntry


@dataclass(frozen=True)
class TtlockBleEnrolledFingerprint:
    """A fingerprint as the lock lists it: its id and the slot holding it."""

    fingerprint_id: bytes
    slot: int

    @classmethod
    def from_entry(cls, entry: FingerprintEntry) -> Self:
        """Take the identity of an entry the SDK read from the lock."""
        return cls(fingerprint_id=entry.fingerprint_id, slot=entry.slot)

    @classmethod
    def from_token(cls, token: str) -> Self | None:
        """Rebuild the identity from `token`, or `None` when it is not one."""
        fingerprint_hex, separator, slot = token.partition("_")
        if not separator or not slot.isdigit():
            return None
        try:
            fingerprint_id = bytes.fromhex(fingerprint_hex)
        except ValueError:
            return None
        return cls(fingerprint_id=fingerprint_id, slot=int(slot))

    @property
    def token(self) -> str:
        """Return the stable text form used in identifiers and unique ids."""
        return f"{self.fingerprint_id.hex()}_{self.slot}"

    @property
    def number(self) -> int:
        """Return the number the official app shows for this fingerprint."""
        return int.from_bytes(self.fingerprint_id + self.slot.to_bytes(2, "big"))
