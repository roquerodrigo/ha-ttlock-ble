"""Actions of the ttlock_ble integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import probatio
from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
from homeassistant.const import WEEKDAYS
from homeassistant.core import SupportsResponse, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_platform_entity_service

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import VolDictType

SERVICE_GET_PASSAGE_MODE = "get_passage_mode"
SERVICE_SET_PASSAGE_MODE = "set_passage_mode"
SERVICE_CLEAR_PASSAGE_MODE = "clear_passage_mode"

ATTR_START_TIME = "start_time"
ATTR_END_TIME = "end_time"
ATTR_DAYS = "days"
ATTR_CLEAR_EXISTING = "clear_existing"


SET_PASSAGE_MODE_SCHEMA: VolDictType = {
    probatio.Required(ATTR_START_TIME): cv.time,
    probatio.Required(ATTR_END_TIME): cv.time,
    probatio.Optional(ATTR_DAYS, default=list(WEEKDAYS)): cv.weekdays,
    probatio.Optional(ATTR_CLEAR_EXISTING, default=False): cv.boolean,
}


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the lock entity actions."""
    async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_GET_PASSAGE_MODE,
        entity_domain=LOCK_DOMAIN,
        schema=None,
        func="async_get_passage_mode",
        supports_response=SupportsResponse.ONLY,
    )
    async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_SET_PASSAGE_MODE,
        entity_domain=LOCK_DOMAIN,
        schema=SET_PASSAGE_MODE_SCHEMA,
        func="async_set_passage_mode",
    )
    async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_CLEAR_PASSAGE_MODE,
        entity_domain=LOCK_DOMAIN,
        schema=None,
        func="async_clear_passage_mode",
    )
