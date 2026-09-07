"""Switch platform for ttlock_ble — the lock's beep."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from ttlock_ble import TTLockError

from .const import LOGGER
from .entity import TtlockBleEntity
from .key_privileges import can_administer

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import VirtualKey

    from .connection import TtlockBleConnection
    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one sound switch per lock this key may administer."""
    data = entry.runtime_data
    async_add_entities(
        TtlockBleSoundSwitch(data.coordinator, key, data.connections[key.lockMac])
        for key in data.virtual_keys
        if can_administer(key)
    )


class TtlockBleSoundSwitch(TtlockBleEntity, SwitchEntity):
    """
    The lock's keypad/lock beep.

    The setting is read from the lock on sessions opened for something
    else and kept by the coordinator, so what the entity shows is what
    the lock last reported — or what it last accepted from here, which
    the next paced read confirms. It is unknown until either has
    happened: nothing connects just to learn it.
    """

    _attr_translation_key = "sound"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:volume-high"

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
        connection: TtlockBleConnection,
    ) -> None:
        """Bind the switch to its key + connection."""
        super().__init__(coordinator, key)
        self._connection = connection

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_sound"

    @property
    def is_on(self) -> bool | None:
        """Return the beep setting as the coordinator last learned it."""
        return self.coordinator.async_sound_enabled(self._key.lockMac)

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn the beep on."""
        await self._async_set(enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn the beep off."""
        await self._async_set(enabled=False)

    async def _async_set(self, *, enabled: bool) -> None:
        """Send the command and adopt what the lock accepted."""
        try:
            await self._connection.async_set_lock_sound(enabled=enabled)
        except TTLockError as exc:
            LOGGER.warning(
                "Failed to set the sound of %s: %s",
                self._key.lockMac,
                exc,
            )
            msg = f"Failed to set the sound of {self._key.lockMac}: {exc}"
            raise HomeAssistantError(msg) from exc
        self.coordinator.async_note_sound_enabled(self._key.lockMac, enabled=enabled)
