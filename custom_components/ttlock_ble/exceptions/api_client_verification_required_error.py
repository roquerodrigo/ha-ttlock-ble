"""Raised when the TTLock cloud demands new-device validation (errcode -1014)."""

from __future__ import annotations

from .api_client_error import TtlockBleApiClientError


class TtlockBleApiClientVerificationRequiredError(TtlockBleApiClientError):
    """
    Raised when the TTLock cloud rejects login with errcode -1014.

    The cloud demands new-device validation: a code is emailed to the
    account holder and `validate_new_device` must succeed before login
    can proceed.
    """
