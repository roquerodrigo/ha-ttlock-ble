"""Exception classes for the ttlock_ble API client."""

from __future__ import annotations

from .api_client_authentication_error import (
    TtlockBleApiClientAuthenticationError,
)
from .api_client_communication_error import (
    TtlockBleApiClientCommunicationError,
)
from .api_client_error import TtlockBleApiClientError
from .api_client_verification_required_error import (
    TtlockBleApiClientVerificationRequiredError,
)

__all__ = [
    "TtlockBleApiClientAuthenticationError",
    "TtlockBleApiClientCommunicationError",
    "TtlockBleApiClientError",
    "TtlockBleApiClientVerificationRequiredError",
]
