from __future__ import annotations

import pytest
from ttlock_ble import FingerprintEntry

from custom_components.ttlock_ble.data import TtlockBleEnrolledFingerprint


def test_the_identity_comes_from_the_sdk_entry() -> None:
    entry = FingerprintEntry(
        fingerprint_id=bytes.fromhex("2f12dd67"),
        slot=0,
        start_date=None,
        end_date=None,
    )

    fingerprint = TtlockBleEnrolledFingerprint.from_entry(entry)

    assert fingerprint == TtlockBleEnrolledFingerprint(bytes.fromhex("2f12dd67"), 0)


def test_the_number_is_the_one_the_official_app_shows() -> None:
    fingerprint = TtlockBleEnrolledFingerprint(bytes.fromhex("2f12dd67"), 0)

    assert fingerprint.number == 51758070431744


def test_the_token_round_trips() -> None:
    fingerprint = TtlockBleEnrolledFingerprint(bytes.fromhex("0000002a"), 1)

    assert fingerprint.token == "0000002a_1"
    assert TtlockBleEnrolledFingerprint.from_token(fingerprint.token) == fingerprint


@pytest.mark.parametrize("token", ["0000002a", "0000002a_", "0000002a_x", "zz_1"])
def test_a_token_that_is_no_fingerprint_is_rejected(token: str) -> None:
    assert TtlockBleEnrolledFingerprint.from_token(token) is None
