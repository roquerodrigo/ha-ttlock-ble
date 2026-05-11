"""Authentication error raised by the API client."""

from __future__ import annotations

from .api_client_error import TtlockBleApiClientError


class TtlockBleApiClientAuthenticationError(
    TtlockBleApiClientError,
):
    """Exception to indicate an authentication error."""
