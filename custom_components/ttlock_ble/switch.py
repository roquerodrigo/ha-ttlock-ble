"""Switch platform for ttlock_ble — the lock's beep."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from ttlock_ble import TTLockError

from .const import LOGGER
from .entity import TtlockBleEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import VirtualKey

    from .connection import TtlockBleConnection
    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry


def _can_manage_sound(key: VirtualKey) -> bool:
    """
    Report whether this key may change lock settings at all.

    The firmware gates the command behind CHECK_ADMIN, which needs both
    an admin key and the admin passcode that authorises it. A key
    obtained outside a TTLock account often carries no passcode, and an
    entity that can only ever fail is worse than no entity.
    """
    return key.is_admin() and bool(key.adminPs)


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
        if _can_manage_sound(key)
    )


class TtlockBleSoundSwitch(TtlockBleEntity, SwitchEntity):
    """
    The lock's keypad/lock beep.

    `assumed_state` because the firmware has no opcode that reports this
    setting back: neither a query nor the advertisement carries it. What
    the entity shows is the last value it sent, which stops being true
    the moment someone changes it from the official app — and is unknown
    entirely until something sets it. Home Assistant renders an assumed
    state as two buttons rather than one toggle, which is the honest
    presentation: the command can be sent, the answer cannot be read.
    """

    _attr_translation_key = "sound"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_assumed_state = True
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
        self._attr_is_on: bool | None = None

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_sound"

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn the beep on."""
        await self._async_set(enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn the beep off."""
        await self._async_set(enabled=False)

    async def _async_set(self, *, enabled: bool) -> None:
        """Send the command and adopt what was sent, since nothing reads it back."""
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
        self._attr_is_on = enabled
        self.async_write_ha_state()
