"""Switch platform for ttlock_ble — the lock's beep."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from ttlock_ble import TTLockError

from .connection import auto_lock_signal, passage_mode_signal
from .const import LOGGER
from .data import TtlockBlePassageSchedule
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
    """Create switches per lock."""
    data = entry.runtime_data
    switches: list[SwitchEntity] = []

    for key in data.virtual_keys:
        conn = data.connections[key.lockMac]
        if _can_manage_sound(key):
            switches.append(
                TtlockBleSoundSwitch(data.coordinator, key, conn)
            )
        switches.append(
            TtlockBleAutoLockSwitch(data.coordinator, key, conn)
        )
        switches.append(
            TtlockBlePassageModeSwitch(data.coordinator, key, conn)
        )

    async_add_entities(switches)


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


class TtlockBleAutoLockSwitch(TtlockBleEntity, SwitchEntity):
    """Toggle auto-lock on or off."""

    _attr_translation_key = "auto_lock"
    _attr_icon = "mdi:lock-clock"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
        connection: TtlockBleConnection,
    ) -> None:
        """Bind to coordinator, key, and connection."""
        super().__init__(coordinator, key)
        self._connection = connection

    @property
    def unique_id(self) -> str:
        """Return a stable unique id."""
        return f"{self._key.lockMac}_auto_lock"

    @property
    def is_on(self) -> bool | None:
        """Return True if auto-lock is currently active."""
        if self._connection.auto_lock_seconds is not None:
            return self._connection.auto_lock_seconds > 0
        return None

    async def async_added_to_hass(self) -> None:
        """Subscribe to auto-lock changes and seed value if not yet read."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                auto_lock_signal(self._key.lockMac),
                self._on_auto_lock_update,
            )
        )
        if self._connection.auto_lock_seconds is None:
            self.hass.async_create_task(self._async_fetch_initial_state())

    @callback
    def _on_auto_lock_update(self, seconds: int) -> None:  # noqa: ARG002
        self.async_write_ha_state()

    async def _async_fetch_initial_state(self) -> None:
        try:
            await self._connection.async_get_auto_lock_info()
        except Exception:  # noqa: BLE001
            pass

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Enable auto-lock with last known duration (or min allowed / 10s)."""
        target = self._connection.last_active_auto_lock or 10
        min_sec = self._connection.auto_lock_limits[0]
        if min_sec is not None and target < min_sec:
            target = min_sec
        try:
            await self._connection.async_set_auto_lock_time(target)
        except TTLockError as exc:
            raise HomeAssistantError(
                f"Failed to enable auto-lock for {self._key.lockMac}: {exc}"
            ) from exc

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Disable auto-lock (set delay to 0)."""
        try:
            await self._connection.async_set_auto_lock_time(0)
        except TTLockError as exc:
            raise HomeAssistantError(
                f"Failed to disable auto-lock for {self._key.lockMac}: {exc}"
            ) from exc


class TtlockBlePassageModeSwitch(TtlockBleEntity, SwitchEntity):
    """Toggle passage mode on or off."""

    _attr_translation_key = "passage_mode"
    _attr_icon = "mdi:door-open"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
        connection: TtlockBleConnection,
    ) -> None:
        """Bind to coordinator, key, and connection."""
        super().__init__(coordinator, key)
        self._connection = connection

    @property
    def unique_id(self) -> str:
        """Return a stable unique id."""
        return f"{self._key.lockMac}_passage_mode"

    @property
    def is_on(self) -> bool | None:
        """Return True if passage mode is currently active."""
        return self._connection.passage_mode_active

    async def async_added_to_hass(self) -> None:
        """Subscribe to passage mode changes and seed status."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                passage_mode_signal(self._key.lockMac),
                self._on_passage_mode_update,
            )
        )
        if self._connection.passage_mode_active is None:
            self.hass.async_create_task(self._async_fetch_initial_state())

    @callback
    def _on_passage_mode_update(self, active: bool) -> None:  # noqa: ARG002
        self.async_write_ha_state()

    async def _async_fetch_initial_state(self) -> None:
        try:
            await self._connection.async_get_passage_mode()
        except Exception:  # noqa: BLE001
            pass

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn on passage mode (sets minimal 1-minute schedule on Monday)."""
        schedule = TtlockBlePassageSchedule(
            type=1,
            week_or_day=1,  # Monday
            month=0,
            start_hour=0,
            start_minute=0,
            end_hour=0,
            end_minute=1,
        )
        try:
            await self._connection.async_set_passage_mode([schedule], clear_existing=True)
        except TTLockError as exc:
            raise HomeAssistantError(
                f"Failed to enable passage mode for {self._key.lockMac}: {exc}"
            ) from exc

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn off passage mode (clear schedules)."""
        try:
            await self._connection.async_clear_passage_mode()
        except TTLockError as exc:
            raise HomeAssistantError(
                f"Failed to disable passage mode for {self._key.lockMac}: {exc}"
            ) from exc
