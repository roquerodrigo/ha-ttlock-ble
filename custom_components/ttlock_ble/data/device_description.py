"""Hardware strings a lock reports over the BLE Device Information Service."""

from __future__ import annotations

from typing import TypedDict


class TtlockBleDeviceDescription(TypedDict):
    """
    Hardware strings a lock reports over the Device Information Service.

    Every value is `str | None`: the service is standard Bluetooth SIG,
    but which characteristics a lock exposes is up to its firmware, and
    the ones it does not answer are absent rather than empty.
    """

    model: str | None
    hardware_version: str | None
    firmware_version: str | None
