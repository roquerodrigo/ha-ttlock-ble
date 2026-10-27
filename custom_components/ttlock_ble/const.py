"""Constants for ttlock_ble."""

from __future__ import annotations

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "ttlock_ble"
MANUFACTURER = "TTLock"
ATTRIBUTION = "Data provided by the TTLock cloud and on-lock BLE"

CONF_PERMANENT_CONNECTION = "permanent_connection"
CONF_CLOUD_APP = "cloud_app"
DEFAULT_CLOUD_APP = "dlock_xp"

CLOUD_ERR_NEW_DEVICE_LOGIN = -1014
HTTP_STATUS_UNAUTHORIZED = frozenset({401, 403})
