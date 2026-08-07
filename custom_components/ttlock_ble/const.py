"""Constants for ttlock_ble."""

from __future__ import annotations

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "ttlock_ble"
MANUFACTURER = "TTLock"
ATTRIBUTION = "Data provided by the TTLock cloud and on-lock BLE"

DEFAULT_SCAN_INTERVAL_SECONDS = 3600
MIN_SCAN_INTERVAL_SECONDS = 60

CONF_RECONNECT_INTERVAL = "reconnect_interval"
CONF_PERMANENT_CONNECTION = "permanent_connection"
DEFAULT_RECONNECT_INTERVAL_SECONDS = 300
MIN_RECONNECT_INTERVAL_SECONDS = 10

CLOUD_ERR_NEW_DEVICE_LOGIN = -1014
HTTP_STATUS_UNAUTHORIZED = frozenset({401, 403})
