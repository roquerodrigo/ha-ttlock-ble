from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.integration_blueprint.api import (
    IntegrationBlueprintApiClient,
    _verify_response_or_raise,
)
from custom_components.integration_blueprint.exceptions import (
    IntegrationBlueprintApiClientAuthenticationError,
    IntegrationBlueprintApiClientCommunicationError,
    IntegrationBlueprintApiClientError,
)


def _make_session(payload=None, side_effect=None, status=200):
    response = AsyncMock()
    response.status = status
    response.raise_for_status = MagicMock()
    response.json = AsyncMock(return_value=payload or {})
    session = MagicMock()
    if side_effect is not None:
        session.request = AsyncMock(side_effect=side_effect)
    else:
        session.request = AsyncMock(return_value=response)
    return session, response


def _client(session) -> IntegrationBlueprintApiClient:
    return IntegrationBlueprintApiClient(username="u", password="p", session=session)


def test_communication_error_is_api_error():
    assert issubclass(
        IntegrationBlueprintApiClientCommunicationError,
        IntegrationBlueprintApiClientError,
    )


def test_auth_error_is_api_error():
    assert issubclass(
        IntegrationBlueprintApiClientAuthenticationError,
        IntegrationBlueprintApiClientError,
    )


def test_api_error_is_exception():
    assert issubclass(IntegrationBlueprintApiClientError, Exception)


def test_verify_response_calls_raise_for_status():
    response = MagicMock()
    response.status = 200
    _verify_response_or_raise(response)
    response.raise_for_status.assert_called_once()


@pytest.mark.parametrize("status", [401, 403])
def test_verify_response_raises_auth_on_401_403(status):
    response = MagicMock()
    response.status = status
    with pytest.raises(IntegrationBlueprintApiClientAuthenticationError):
        _verify_response_or_raise(response)


def test_verify_response_propagates_http_error():
    response = MagicMock()
    response.status = 500
    response.raise_for_status.side_effect = aiohttp.ClientResponseError(
        request_info=MagicMock(), history=()
    )
    with pytest.raises(aiohttp.ClientResponseError):
        _verify_response_or_raise(response)


async def test_async_get_data_returns_payload(sample_payload):
    session, _ = _make_session(sample_payload)
    result = await _client(session).async_get_data()
    assert result == sample_payload


async def test_async_get_data_uses_correct_url():
    from custom_components.integration_blueprint.const import API_BASE_URL

    session, _ = _make_session({})
    await _client(session).async_get_data()
    assert session.request.call_args.kwargs["url"] == f"{API_BASE_URL}/posts/1"
    assert session.request.call_args.kwargs["method"] == "get"


async def test_async_set_title_sends_patch():
    session, _ = _make_session({})
    await _client(session).async_set_title("hello")
    assert session.request.call_args.kwargs["method"] == "patch"
    assert session.request.call_args.kwargs["json"] == {"title": "hello"}


async def test_api_wrapper_timeout_raises_communication_error():
    session, _ = _make_session(side_effect=TimeoutError("timed out"))
    with pytest.raises(
        IntegrationBlueprintApiClientCommunicationError, match="Timeout"
    ):
        await _client(session)._api_wrapper(method="get", url="http://x")


async def test_api_wrapper_client_error_raises_communication_error():
    session, _ = _make_session(side_effect=aiohttp.ClientError("refused"))
    with pytest.raises(
        IntegrationBlueprintApiClientCommunicationError, match="Error fetching"
    ):
        await _client(session)._api_wrapper(method="get", url="http://x")


async def test_api_wrapper_socket_error_raises_communication_error():
    session, _ = _make_session(side_effect=socket.gaierror("dns"))
    with pytest.raises(
        IntegrationBlueprintApiClientCommunicationError, match="Error fetching"
    ):
        await _client(session)._api_wrapper(method="get", url="http://x")


async def test_api_wrapper_unexpected_exception_raises_api_error():
    session, _ = _make_session(side_effect=RuntimeError("boom"))
    with pytest.raises(
        IntegrationBlueprintApiClientError, match="Something really wrong"
    ):
        await _client(session)._api_wrapper(method="get", url="http://x")


async def test_api_wrapper_auth_status_raises_auth_error():
    session, _ = _make_session(status=401)
    with pytest.raises(IntegrationBlueprintApiClientAuthenticationError):
        await _client(session)._api_wrapper(method="get", url="http://x")


async def test_api_wrapper_returns_json_on_success(sample_payload):
    session, _ = _make_session(sample_payload)
    result = await _client(session)._api_wrapper(method="get", url="http://x")
    assert result == sample_payload
