"""One credential a lock is known to hold."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Self

from ..credential_type import TtlockBleCredentialType
from .enrolled_fingerprint import TtlockBleEnrolledFingerprint

if TYPE_CHECKING:
    from ttlock_ble import CardEntry, FingerprintEntry

PASSCODE_MASK = "•••"

# Enough to make a stored key costly to reverse one code at a time, little
# enough to derive on the event loop; each code is derived once per run.
PASSCODE_KEY_ITERATIONS = 10_000

# The first digit and the last two are shown, so a shorter code would have
# nothing left to hide.
MIN_MASKED_PASSCODE_LENGTH = 4


@dataclass(frozen=True)
class TtlockBleKnownCredential:
    """
    A credential as this integration tracks it: what it is, and how to show it.

    `key` is what the credential is stored and matched under, and `label`
    is what the user sees. They differ for a passcode only: its key is a
    digest of the code and its label keeps just the first digit and the
    last two, because the code itself opens the door and must never reach
    an entity name, a state or an attribute.
    """

    credential_type: TtlockBleCredentialType
    key: str
    label: str

    @classmethod
    def from_fingerprint(cls, entry: FingerprintEntry) -> Self:
        """Track a fingerprint the lock listed, under the number the app shows."""
        fingerprint = TtlockBleEnrolledFingerprint.from_entry(entry)
        return cls(
            credential_type=TtlockBleCredentialType.FINGERPRINT,
            key=fingerprint.token,
            label=str(fingerprint.number),
        )

    @classmethod
    def from_card(cls, entry: CardEntry) -> Self:
        """Track a card the lock listed, under the number its log records carry."""
        number = str(int.from_bytes(entry.card_id, "big"))
        return cls(
            credential_type=TtlockBleCredentialType.CARD, key=number, label=number
        )

    @classmethod
    def from_passcode(cls, mac: str, passcode: str) -> Self:
        """Track a passcode by a digest of it, labelled with three of its digits."""
        return cls(
            credential_type=TtlockBleCredentialType.PASSCODE,
            key=passcode_key(mac, passcode),
            label=_masked(passcode),
        )


@lru_cache(maxsize=256)
def passcode_key(mac: str, passcode: str) -> str:
    """
    Return the key a passcode is stored under on the lock `mac`.

    A key derivation keeps the code out of the store in clear, salted
    with the lock's MAC. It only slows down whoever holds the file, since
    a keypad code is short enough to try every value, but that file sits
    next to the lock's own keys.
    """
    return hashlib.pbkdf2_hmac(
        "sha256",
        passcode.encode(),
        mac.upper().encode(),
        PASSCODE_KEY_ITERATIONS,
    ).hex()[:32]


def _masked(passcode: str) -> str:
    if len(passcode) < MIN_MASKED_PASSCODE_LENGTH:
        return PASSCODE_MASK
    return f"{passcode[0]}{PASSCODE_MASK}{passcode[-2:]}"
