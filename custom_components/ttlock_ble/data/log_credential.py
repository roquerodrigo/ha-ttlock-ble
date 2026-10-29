"""The credential behind one operation-log record."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..credential_type import TtlockBleCredentialType


@dataclass(frozen=True)
class TtlockBleLogCredential:
    """
    What a record says about the credential it was made with.

    Each part is `None` when the record does not carry it: `identifier`
    is withheld for passcodes, since the value would be the door code
    itself, and `name` is only known for what the user named.
    """

    credential_type: TtlockBleCredentialType | None
    identifier: str | None
    name: str | None
