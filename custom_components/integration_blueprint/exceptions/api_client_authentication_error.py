"""Authentication error raised by the API client."""

from __future__ import annotations

from .api_client_error import IntegrationBlueprintApiClientError


class IntegrationBlueprintApiClientAuthenticationError(
    IntegrationBlueprintApiClientError,
):
    """Exception to indicate an authentication error."""
