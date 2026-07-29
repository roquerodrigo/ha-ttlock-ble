from __future__ import annotations

from custom_components.ttlock_ble.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def test_diagnostics_redacts_username(hass, setup_integration) -> None:
    diag = await async_get_config_entry_diagnostics(hass, setup_integration)
    assert diag["entry"]["data"]["username"] == "**REDACTED**"


async def test_diagnostics_redacts_password(hass, setup_integration) -> None:
    diag = await async_get_config_entry_diagnostics(hass, setup_integration)
    assert diag["entry"]["data"]["password"] == "**REDACTED**"


async def test_diagnostics_redacts_keys(hass, setup_integration) -> None:
    diag = await async_get_config_entry_diagnostics(hass, setup_integration)
    assert diag["entry"]["data"]["keys"] == "**REDACTED**"


async def test_diagnostics_includes_entry_metadata(hass, setup_integration) -> None:
    diag = await async_get_config_entry_diagnostics(hass, setup_integration)
    assert diag["entry"]["domain"] == "ttlock_ble"
    assert diag["entry"]["version"] == 1
    assert "title" in diag["entry"]


async def test_diagnostics_includes_lock_summary(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    diag = await async_get_config_entry_diagnostics(hass, setup_integration)
    assert len(diag["locks"]) == 1
    lock = diag["locks"][0]
    assert lock["lockMac"] == sample_virtual_key.lockMac
    assert lock["lockAlias"] == sample_virtual_key.lockAlias
    assert lock["lockId"] == sample_virtual_key.lockId


async def test_diagnostics_lock_summary_omits_secrets(hass, setup_integration) -> None:
    diag = await async_get_config_entry_diagnostics(hass, setup_integration)
    lock = diag["locks"][0]
    assert "aesKeyStr" not in lock
    assert "unlockKey" not in lock
    assert "adminPs" not in lock


async def test_diagnostics_includes_coordinator_state(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    diag = await async_get_config_entry_diagnostics(hass, setup_integration)
    state = diag["coordinator_state"][sample_virtual_key.lockMac]
    assert state["available"] is True
    assert state["locked"] is True


async def test_diagnostics_options_block_is_a_dict(hass, setup_integration) -> None:
    diag = await async_get_config_entry_diagnostics(hass, setup_integration)
    assert isinstance(diag["entry"]["options"], dict)


async def test_diagnostics_reports_no_advertisement_when_unseen(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    from custom_components.ttlock_ble.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, setup_integration)
    assert diagnostics["advertisements"][sample_virtual_key.lockMac] is None


async def test_diagnostics_carries_the_raw_advertisement_bytes(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    """The dump keeps the raw payload so an undecodable layout stays diagnosable."""
    from unittest.mock import MagicMock, patch

    from custom_components.ttlock_ble.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    payload = bytes([2, 0x01, 77, 0, 0, 0, 0]) + bytes.fromhex("ffeeddccbbaa")
    service_info = MagicMock()
    service_info.source = "hci0"
    service_info.rssi = -61
    service_info.manufacturer_data = {0x0305: payload}
    with patch(
        "custom_components.ttlock_ble.diagnostics.async_last_service_info",
        return_value=service_info,
    ):
        diagnostics = await async_get_config_entry_diagnostics(hass, setup_integration)

    captured = diagnostics["advertisements"][sample_virtual_key.lockMac]
    assert captured["rssi"] == -61
    assert captured["manufacturer_data"] == {"773": payload.hex()}
    assert captured["decoded"]["lock_state"] == "UNLOCKED"
    assert captured["decoded"]["battery"] == 77


async def test_diagnostics_decoded_is_none_for_a_foreign_payload(
    hass,
    setup_integration,
    sample_virtual_key,
) -> None:
    from unittest.mock import MagicMock, patch

    from custom_components.ttlock_ble.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    service_info = MagicMock()
    service_info.source = "hci0"
    service_info.rssi = -80
    service_info.manufacturer_data = {0x004C: b"\x02\x15"}
    with patch(
        "custom_components.ttlock_ble.diagnostics.async_last_service_info",
        return_value=service_info,
    ):
        diagnostics = await async_get_config_entry_diagnostics(hass, setup_integration)

    assert diagnostics["advertisements"][sample_virtual_key.lockMac]["decoded"] is None
