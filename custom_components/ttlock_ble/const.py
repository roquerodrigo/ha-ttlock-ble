"""Constants for ttlock_ble."""

from __future__ import annotations

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "ttlock_ble"
MANUFACTURER = "TTLock"
ATTRIBUTION = "Data provided by the TTLock cloud and on-lock BLE"

DEFAULT_SCAN_INTERVAL_SECONDS = 3600
MIN_SCAN_INTERVAL_SECONDS = 60

CLOUD_ERR_NEW_DEVICE_LOGIN = -1014
