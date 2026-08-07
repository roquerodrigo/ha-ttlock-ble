"""
TTLock BLE cloud-bootstrap client.

Wraps `ttlock_ble.TTLockCloud` so the config flow and entry setup only
see the integration's own exception hierarchy. Calls run through a
shared `httpx.AsyncClient` supplied by Home Assistant; cleanup of that
client stays with the caller.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import httpx

from ttlock_ble import CloudError, TTLockCloud

from .const import CLOUD_ERR_NEW_DEVICE_LOGIN, HTTP_STATUS_UNAUTHORIZED
from .exceptions import (
    TtlockBleApiClientAuthenticationError,
    TtlockBleApiClientCommunicationError,
    TtlockBleApiClientError,
    TtlockBleApiClientVerificationRequiredError,
)

if TYPE_CHECKING:
    from ttlock_ble import VirtualKey


class TtlockBleApiClient:
    """Thin async wrapper around `TTLockCloud` for the integration."""

    def __init__(self, *, httpx_client: httpx.AsyncClient) -> None:
        """Bind to a Home-Assistant-managed `httpx.AsyncClient`."""
        self._cloud = TTLockCloud(client=httpx_client)

    async def async_login(self, username: str, password: str) -> None:
        """Discover the regional endpoint and log into the TTLock cloud."""
        try:
            with contextlib.suppress(CloudError):
                await self._cloud.discover_site()
            await self._cloud.login(username, password)
        except CloudError as exc:
            raise self._classify_cloud_error(exc) from exc
        except httpx.HTTPError as exc:
            msg = f"Failed to reach TTLock cloud: {exc}"
            raise TtlockBleApiClientCommunicationError(msg) from exc

    async def async_request_verification_code(self, account: str) -> None:
        """Ask the cloud to email a new-device-login code to `account`."""
        try:
            await self._cloud.request_login_verification_code(account)
        except CloudError as exc:
            raise self._classify_cloud_error(exc) from exc
        except httpx.HTTPError as exc:
            msg = f"Failed to reach TTLock cloud: {exc}"
            raise TtlockBleApiClientCommunicationError(msg) from exc

    async def async_validate_new_device_and_login(
        self,
        username: str,
        password: str,
        verification_code: str,
    ) -> None:
        """Submit the verification code, then complete the login."""
        try:
            await self._cloud.validate_new_device(username, verification_code)
            await self._cloud.login(username, password)
        except CloudError as exc:
            raise self._classify_cloud_error(exc) from exc
        except httpx.HTTPError as exc:
            msg = f"Failed to reach TTLock cloud: {exc}"
            raise TtlockBleApiClientCommunicationError(msg) from exc

    async def async_list_keys(self) -> list[VirtualKey]:
        """Page through `/check/syncDataPage` and return every key for this user."""
        try:
            return await self._cloud.list_keys()
        except CloudError as exc:
            raise self._classify_cloud_error(exc) from exc
        except httpx.HTTPError as exc:
            msg = f"Failed to reach TTLock cloud: {exc}"
            raise TtlockBleApiClientCommunicationError(msg) from exc

    @staticmethod
    def _classify_cloud_error(exc: CloudError) -> TtlockBleApiClientError:
        """
        Map a `CloudError` onto the integration's exception hierarchy.

        The SDK raises `CloudError` for two distinct things: the cloud
        answering with a non-zero `errcode`, and any HTTP status at or
        above 400 whose body it could not parse (which it reports as
        `http_status`). Only the first says anything about the
        credentials. Treating both as an authentication failure — the
        previous behaviour — told users to rotate a working password
        during a cloud outage or a rate limit, and looped reauth.

        Anything the body does not identify stays the base error, which
        the config flow shows as "unknown" rather than blaming the
        password.
        """
        body = exc.body
        status = body.get("http_status")
        if isinstance(status, int):
            if status in HTTP_STATUS_UNAUTHORIZED:
                return TtlockBleApiClientAuthenticationError(str(exc))
            return TtlockBleApiClientCommunicationError(str(exc))
        errcode = body.get("errorCode") or body.get("errcode")
        if errcode == CLOUD_ERR_NEW_DEVICE_LOGIN:
            return TtlockBleApiClientVerificationRequiredError(str(exc))
        if errcode is not None:
            return TtlockBleApiClientAuthenticationError(str(exc))
        return TtlockBleApiClientError(str(exc))
