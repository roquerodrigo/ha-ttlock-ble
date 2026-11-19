"""Switch platform for ttlock_ble — the lock's beep and its passage mode."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from ttlock_ble import TTLockError

from .const import DOMAIN, LOGGER
from .entity import TtlockBleEntity
from .key_privileges import can_administer, can_manage_passage_mode
from .passage_mode import always_slots
from .switch_slot_store import async_get_switch_slot_store

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import VirtualKey

    from .connection import TtlockBleConnection
    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry
    from .switch_slot_store import TtlockBleSwitchSlotStore


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the sound and passage mode switches per lock this key may administer."""
    data = entry.runtime_data
    slots = await async_get_switch_slot_store(hass)
    async_add_entities(
        switch
        for key in data.virtual_keys
        if can_administer(key)
        for switch in (
            TtlockBleSoundSwitch(data.coordinator, key, data.connections[key.lockMac]),
            *(
                (
                    TtlockBlePassageModeSwitch(
                        data.coordinator,
                        key,
                        data.connections[key.lockMac],
                        slots,
                    ),
                )
                if can_manage_passage_mode(key)
                else ()
            ),
        )
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


class TtlockBlePassageModeSwitch(TtlockBleEntity, SwitchEntity):
    """
    Passage mode left on, with no end: the lock stops relocking on its own.

    Turning it on writes one all-day slot for every weekday next to
    whatever the lock already holds, and turning it off removes those and
    nothing else, so a schedule set in the official app or through
    `set_passage_mode` survives either. The slots it wrote are recorded
    (see `TtlockBleSwitchSlotStore`) because the lock cannot say who wrote
    one; two identical slots cannot be told apart, so one that matches
    exactly is treated as ours. Neither direction moves the bolt, as the
    official app's own toggle does not: once on, the lock stays unlocked
    from the next time it is unlocked.

    It is on while the slots it wrote are in place, and says nothing
    about a schedule somebody else set - the passage mode binary sensor
    is what says whether a slot is in effect right now.
    """

    _attr_translation_key = "passage_mode"
    _attr_icon = "mdi:door-open"

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
        connection: TtlockBleConnection,
        slots: TtlockBleSwitchSlotStore,
    ) -> None:
        """Bind the switch to its key, its connection and its record of slots."""
        super().__init__(coordinator, key)
        self._connection = connection
        self._owned = slots

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_passage_mode_switch"

    @property
    def is_on(self) -> bool:
        """Return whether the slots this switch wrote are in place."""
        owned = self._owned.get(self._key.lockMac)
        if not owned:
            return False
        listed = self.coordinator.async_passage_slots(self._key.lockMac)
        return listed is None or all(slot in listed for slot in owned)

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Leave passage mode on at all times, next to the slots already there."""
        mac = self._key.lockMac
        owned = self._owned.get(mac)
        try:
            for slot in always_slots():
                if slot in owned:
                    continue
                owned.append(slot)
                await self._owned.async_remember(mac, owned)
                try:
                    await self._connection.async_add_passage_slot(slot)
                except TTLockError:
                    owned.remove(slot)
                    await self._owned.async_remember(mac, owned)
                    raise
        except TTLockError as exc:
            await self._async_remove_owned()
            raise self._failure(exc) from exc
        finally:
            await self._async_settle()

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Remove the slots this switch wrote, and leave every other one."""
        try:
            await self._async_remove_owned()
        except TTLockError as exc:
            raise self._failure(exc) from exc
        finally:
            await self._async_settle()

    async def _async_remove_owned(self) -> None:
        """
        Delete the slots this switch owns, forgetting each as it goes.

        The record shrinks with the lock, so a retry after a failure never
        asks for a slot that is already gone, which the lock may answer
        as a failure.
        """
        mac = self._key.lockMac
        owned = self._owned.get(mac)
        for slot in list(owned):
            await self._connection.async_delete_passage_slot(slot)
            owned.remove(slot)
            await self._owned.async_remember(mac, owned)

    async def _async_settle(self) -> None:
        """Read back what the lock now holds and publish the switch."""
        await self.coordinator.async_refresh_passage_slots(self._key.lockMac)
        self.async_write_ha_state()

    def _failure(self, exc: TTLockError) -> HomeAssistantError:
        """Log a failed change and build what the user sees."""
        LOGGER.warning(
            "Failed to change the passage mode of %s: %s",
            self._key.lockMac,
            exc,
        )
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="passage_mode_failed",
            translation_placeholders={"lock": self._lock_name},
        )
