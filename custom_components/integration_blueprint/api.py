"""Integration Blueprint API Client."""

from __future__ import annotations

import asyncio
import socket
from typing import TYPE_CHECKING, cast

import aiohttp

from .const import API_BASE_URL
from .exceptions import (
    IntegrationBlueprintApiClientAuthenticationError,
    IntegrationBlueprintApiClientCommunicationError,
    IntegrationBlueprintApiClientError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .data import IntegrationBlueprintPost, JsonObject, JsonValue


def _verify_response_or_raise(response: aiohttp.ClientResponse) -> None:
    """Verify that the response is valid."""
    if response.status in (401, 403):
        msg = "Invalid credentials"
        raise IntegrationBlueprintApiClientAuthenticationError(msg)
    response.raise_for_status()


class IntegrationBlueprintApiClient:
    """Sample API Client. Replace with your real client."""

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize."""
        self._username = username
        self._password = password
        self._session = session

    async def async_get_data(self) -> IntegrationBlueprintPost:
        """Get a sample post from the API."""
        raw = await self._api_wrapper(
            method="get",
            url=f"{API_BASE_URL}/posts/1",
        )
        return cast("IntegrationBlueprintPost", raw)

    async def async_set_title(self, value: str) -> IntegrationBlueprintPost:
        """Send a sample PATCH that updates the post title."""
        raw = await self._api_wrapper(
            method="patch",
            url=f"{API_BASE_URL}/posts/1",
            data={"title": value},
            headers={"Content-type": "application/json; charset=UTF-8"},
        )
        return cast("IntegrationBlueprintPost", raw)

    async def _api_wrapper(
        self,
        method: str,
        url: str,
        data: Mapping[str, JsonValue] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> JsonObject:
        """Perform an HTTP request and return the parsed JSON object."""
        try:
            async with asyncio.timeout(10):
                response = await self._session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data,
                )
                _verify_response_or_raise(response)
                return cast("JsonObject", await response.json())

        except TimeoutError as exception:
            msg = f"Timeout error fetching information - {exception}"
            raise IntegrationBlueprintApiClientCommunicationError(msg) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error fetching information - {exception}"
            raise IntegrationBlueprintApiClientCommunicationError(msg) from exception
        except IntegrationBlueprintApiClientError:
            raise
        except Exception as exception:  # pylint: disable=broad-except
            msg = f"Something really wrong happened! - {exception}"
            raise IntegrationBlueprintApiClientError(msg) from exception
