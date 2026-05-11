"""IntegrationBlueprintEntity base class."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import IntegrationBlueprintDataUpdateCoordinator


class IntegrationBlueprintEntity(
    CoordinatorEntity[IntegrationBlueprintDataUpdateCoordinator]
):
    """Base entity for Integration Blueprint."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the single integration device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name="Integration Blueprint",
            manufacturer="Integration Blueprint",
        )
