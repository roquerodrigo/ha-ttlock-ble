from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ttlock_ble import VirtualKey
from ttlock_ble.models.lock_version import LockVersion

# Eagerly import the integration submodules so `unittest.mock.patch` can
# resolve dotted targets like `custom_components.ttlock_ble.api.TTLockCloud`
# under pytest. Without this, Python's namespace package (custom_components/
# has no __init__.py) leaves `ttlock_ble` unbound as an attribute, and
# `pkgutil.resolve_name` fails with `module 'custom_components' has no
# attribute 'ttlock_ble'` once HA's bluetooth loader runs.
import custom_components.ttlock_ble
import custom_components.ttlock_ble.api
import custom_components.ttlock_ble.connection
import custom_components.ttlock_ble.coordinator
import custom_components.ttlock_ble.lock  # noqa: F401

if TYPE_CHECKING:
    from collections.abc import Generator

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def expected_lingering_timers() -> bool:
    """Allow HA bluetooth scanner timers to outlive each test.

    `enable_bluetooth` loads the HA bluetooth integration whose scanner
    schedules a periodic `_async_expire_devices_schedule_next` timer that
    survives the integration unload. Until HA tightens that cleanup, we
    opt out of the lingering-timer guard.
    """
    return True


@pytest.fixture(autouse=True)
def _fast_command_settle() -> Generator[None]:
    """Make the lock entity's post-command settle window finish instantly.

    The production default (4s) would tack 4 real seconds onto every
    test that fires a lock/unlock service call and then asserts on the
    resulting UI state. Individual tests can re-patch this constant
    with their own value inside a tighter context.
    """
    with patch(
        "custom_components.ttlock_ble.lock.COMMAND_SETTLE_SECONDS",
        0.001,
    ):
        yield


@pytest.fixture
def enable_custom_integrations(hass, enable_bluetooth) -> None:
    """Clear the custom-component cache and bring up the bluetooth stub."""
    from homeassistant.loader import DATA_CUSTOM_COMPONENTS

    hass.data.pop(DATA_CUSTOM_COMPONENTS, None)


@pytest.fixture
def sample_virtual_key() -> VirtualKey:
    return VirtualKey(
        keyId=1,
        lockId=42,
        lockMac="AA:BB:CC:DD:EE:FF",
        lockAlias="Front door",
        lockName="Front",
        lockVersion=LockVersion(
            protocolType=5,
            protocolVersion=3,
            scene=2,
            groupId=0,
            orgId=0,
        ),
        aesKeyStr="0123456789abcdef" * 2,
        unlockKey="123456",
        lockFlagPos=0,
        timezoneRawOffSet=-180,
        keyType=1,
        userType="110301",
        adminPs="999999",
        uid=1234,
    )


@pytest.fixture
def sample_stored_key(sample_virtual_key: VirtualKey) -> dict:
    return sample_virtual_key.to_dict()


@pytest.fixture
def mock_cloud() -> Generator[MagicMock]:
    """Patch `TTLockCloud` as imported by `api.py`, return the instance mock."""
    with patch("custom_components.ttlock_ble.api.TTLockCloud") as cls:
        instance = MagicMock()
        instance.discover_site = AsyncMock(return_value={})
        instance.login = AsyncMock(
            return_value=MagicMock(
                uid=1234, access_token="tok", username="user@example.com"
            ),
        )
        instance.request_login_verification_code = AsyncMock(return_value={})
        instance.validate_new_device = AsyncMock(return_value={})
        instance.list_keys = AsyncMock(return_value=[])
        instance.aclose = AsyncMock(return_value=None)
        instance.creds = MagicMock(uid=1234, access_token="tok")
        cls.return_value = instance
        yield instance


@pytest.fixture
def mock_ble_device() -> MagicMock:
    """Stand-in for a `BLEDevice` handed out by HA's bluetooth manager."""
    device = MagicMock(name="BLEDevice")
    device.address = "AA:BB:CC:DD:EE:FF"
    return device


@pytest.fixture
def mock_ble_resolver(mock_ble_device: MagicMock) -> Generator[MagicMock]:
    """Patch `async_ble_device_from_address` in `connection.py`."""
    resolver = MagicMock(return_value=mock_ble_device)
    with patch(
        "custom_components.ttlock_ble.connection.async_ble_device_from_address",
        new=resolver,
    ):
        yield resolver


@pytest.fixture
def mock_ttlock_client() -> Generator[MagicMock]:
    """Patch `TTLockClient.from_ble_device` returning a controllable mock."""
    instance = MagicMock(name="TTLockClient")
    instance.connect = AsyncMock(return_value=None)
    instance.disconnect = AsyncMock(return_value=None)
    instance.query_state = AsyncMock(return_value=(0, 80))
    instance.lock = AsyncMock(return_value=None)
    instance.unlock = AsyncMock(return_value=None)
    with patch("custom_components.ttlock_ble.connection.TTLockClient") as cls:
        cls.from_ble_device = MagicMock(return_value=instance)
        yield instance


@pytest.fixture
def mock_ttlock_connection() -> Generator[MagicMock]:
    """Mock the whole `TtlockBleConnection` class at the integration setup site."""
    instance = MagicMock(name="TtlockBleConnection")
    instance.async_query_state = AsyncMock(return_value=(0, 80))
    instance.async_lock = AsyncMock(return_value=None)
    instance.async_unlock = AsyncMock(return_value=None)
    with patch("custom_components.ttlock_ble.TtlockBleConnection") as cls:
        cls.return_value = instance
        yield instance


@pytest.fixture
async def setup_integration(
    hass,
    enable_bluetooth,
    enable_custom_integrations,
    sample_stored_key,
    mock_cloud,
    mock_ttlock_connection,
):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ttlock_ble.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "username": "user@example.com",
            "password": "pass",
            "keys": [sample_stored_key],
        },
        unique_id="user_example_com",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
