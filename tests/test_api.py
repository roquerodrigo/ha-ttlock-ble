from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from ttlock_ble import CloudError

from custom_components.ttlock_ble.api import TtlockBleApiClient
from custom_components.ttlock_ble.exceptions import (
    TtlockBleApiClientAuthenticationError,
    TtlockBleApiClientCommunicationError,
    TtlockBleApiClientError,
    TtlockBleApiClientVerificationRequiredError,
)


def _client(mock_cloud: MagicMock) -> TtlockBleApiClient:
    """Wrap the patched TTLockCloud instance in a fresh TtlockBleApiClient."""
    # Pass a sentinel httpx client; mock_cloud is the value cls(client=...) returns.
    return TtlockBleApiClient(httpx_client=MagicMock(spec=httpx.AsyncClient))


def test_communication_error_is_api_error() -> None:
    assert issubclass(
        TtlockBleApiClientCommunicationError,
        TtlockBleApiClientError,
    )


def test_auth_error_is_api_error() -> None:
    assert issubclass(
        TtlockBleApiClientAuthenticationError,
        TtlockBleApiClientError,
    )


def test_verification_required_is_api_error() -> None:
    assert issubclass(
        TtlockBleApiClientVerificationRequiredError,
        TtlockBleApiClientError,
    )


def test_api_error_is_exception() -> None:
    assert issubclass(TtlockBleApiClientError, Exception)


async def test_login_happy_path(mock_cloud: MagicMock) -> None:
    await _client(mock_cloud).async_login("user@example.com", "pw")
    mock_cloud.discover_site.assert_awaited_once()
    mock_cloud.login.assert_awaited_once_with("user@example.com", "pw")


async def test_login_swallows_discover_site_cloud_error(mock_cloud: MagicMock) -> None:
    mock_cloud.discover_site = AsyncMock(side_effect=CloudError({"errmsg": "no site"}))
    await _client(mock_cloud).async_login("u", "p")
    mock_cloud.login.assert_awaited_once_with("u", "p")


async def test_login_maps_minus_1014_to_verification_required(
    mock_cloud: MagicMock,
) -> None:
    mock_cloud.login = AsyncMock(
        side_effect=CloudError({"errorCode": -1014, "errmsg": "new device"}),
    )
    with pytest.raises(TtlockBleApiClientVerificationRequiredError):
        await _client(mock_cloud).async_login("u", "p")


async def test_login_maps_other_cloud_error_to_auth(mock_cloud: MagicMock) -> None:
    mock_cloud.login = AsyncMock(
        side_effect=CloudError({"errorCode": -2003, "errmsg": "bad password"}),
    )
    with pytest.raises(TtlockBleApiClientAuthenticationError):
        await _client(mock_cloud).async_login("u", "p")


async def test_login_maps_httpx_error_to_communication(mock_cloud: MagicMock) -> None:
    mock_cloud.login = AsyncMock(side_effect=httpx.ConnectError("no route"))
    with pytest.raises(TtlockBleApiClientCommunicationError, match="Failed to reach"):
        await _client(mock_cloud).async_login("u", "p")


async def test_request_verification_code_happy(mock_cloud: MagicMock) -> None:
    await _client(mock_cloud).async_request_verification_code("user@example.com")
    mock_cloud.request_login_verification_code.assert_awaited_once_with(
        "user@example.com"
    )


async def test_request_verification_code_cloud_error_becomes_auth(
    mock_cloud: MagicMock,
) -> None:
    mock_cloud.request_login_verification_code = AsyncMock(
        side_effect=CloudError({"errmsg": "blocked"}),
    )
    with pytest.raises(TtlockBleApiClientAuthenticationError):
        await _client(mock_cloud).async_request_verification_code("x")


async def test_request_verification_code_httpx_error_becomes_communication(
    mock_cloud: MagicMock,
) -> None:
    mock_cloud.request_login_verification_code = AsyncMock(
        side_effect=httpx.ReadTimeout("slow"),
    )
    with pytest.raises(TtlockBleApiClientCommunicationError):
        await _client(mock_cloud).async_request_verification_code("x")


async def test_validate_new_device_happy(mock_cloud: MagicMock) -> None:
    await _client(mock_cloud).async_validate_new_device_and_login(
        "user", "pw", "123456"
    )
    mock_cloud.validate_new_device.assert_awaited_once_with("user", "123456")
    mock_cloud.login.assert_awaited_once_with("user", "pw")


async def test_validate_new_device_cloud_error_becomes_auth(
    mock_cloud: MagicMock,
) -> None:
    mock_cloud.validate_new_device = AsyncMock(
        side_effect=CloudError({"errmsg": "bad code"}),
    )
    with pytest.raises(TtlockBleApiClientAuthenticationError):
        await _client(mock_cloud).async_validate_new_device_and_login(
            "u", "p", "000000"
        )


async def test_validate_new_device_httpx_error_becomes_communication(
    mock_cloud: MagicMock,
) -> None:
    mock_cloud.validate_new_device = AsyncMock(side_effect=httpx.ConnectError("no dns"))
    with pytest.raises(TtlockBleApiClientCommunicationError):
        await _client(mock_cloud).async_validate_new_device_and_login("u", "p", "1")


async def test_list_keys_returns_what_cloud_returns(
    mock_cloud: MagicMock,
    sample_virtual_key,
) -> None:
    mock_cloud.list_keys = AsyncMock(return_value=[sample_virtual_key])
    result = await _client(mock_cloud).async_list_keys()
    assert result == [sample_virtual_key]


async def test_list_keys_cloud_error_becomes_auth(mock_cloud: MagicMock) -> None:
    mock_cloud.list_keys = AsyncMock(side_effect=CloudError({"errmsg": "session"}))
    with pytest.raises(TtlockBleApiClientAuthenticationError):
        await _client(mock_cloud).async_list_keys()


async def test_list_keys_httpx_error_becomes_communication(
    mock_cloud: MagicMock,
) -> None:
    mock_cloud.list_keys = AsyncMock(side_effect=httpx.ConnectError("x"))
    with pytest.raises(TtlockBleApiClientCommunicationError):
        await _client(mock_cloud).async_list_keys()


def test_credentials_property_returns_cloud_creds(mock_cloud: MagicMock) -> None:
    assert _client(mock_cloud).credentials is mock_cloud.creds


def test_classify_falls_back_to_auth_when_no_errcode(mock_cloud: MagicMock) -> None:
    err = CloudError({"http_status": 500, "text": "boom"})
    classified = TtlockBleApiClient._classify_cloud_error(err)
    assert isinstance(classified, TtlockBleApiClientAuthenticationError)
