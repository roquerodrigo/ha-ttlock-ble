"""Button platform for ttlock_ble — reading the credential lists on demand."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .entity import TtlockBleEntity
from .key_privileges import can_administer

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .data import TtlockBleConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one credential-refresh button per lock this key may administer."""
    data = entry.runtime_data
    async_add_entities(
        TtlockBleRefreshCredentialsButton(data.coordinator, key)
        for key in data.virtual_keys
        if can_administer(key)
    )


class TtlockBleRefreshCredentialsButton(TtlockBleEntity, ButtonEntity):
    """
    Reads the credential lists now instead of on the next paced session.

    No advertisement or push event tells a credential change apart from
    any other record, so nothing could trigger this read on its own
    without polling the lock.
    """

    _attr_translation_key = "refresh_credentials"
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_refresh_credentials"

    async def async_press(self) -> None:
        """Read the lists, and fail visibly when the lock could not be reached."""
        if not await self.coordinator.async_refresh_credentials(self._key.lockMac):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="credentials_not_read",
                translation_placeholders={"lock": self._lock_name},
            )
