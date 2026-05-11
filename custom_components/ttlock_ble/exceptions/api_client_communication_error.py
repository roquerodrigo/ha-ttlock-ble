"""Communication error raised by the API client."""

from __future__ import annotations

from .api_client_error import TtlockBleApiClientError


class TtlockBleApiClientCommunicationError(
    TtlockBleApiClientError,
):
    """Exception to indicate a communication error."""
