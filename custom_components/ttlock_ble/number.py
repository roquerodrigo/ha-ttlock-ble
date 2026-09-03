"""Number platform for ttlock_ble — auto-lock delay slider."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from ttlock_ble import TTLockError

from .connection import auto_lock_signal
from .entity import TtlockBleEntity

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
    """Create auto-lock number entity for each VirtualKey."""
    data = entry.runtime_data
    async_add_entities(
        TtlockBleAutoLockTimeNumber(
            data.coordinator,
            key,
            data.connections[key.lockMac],
        )
        for key in data.virtual_keys
    )


class TtlockBleAutoLockTimeNumber(TtlockBleEntity, NumberEntity):
    """Auto-lock duration slider in seconds (0 = disabled)."""

    _attr_translation_key = "auto_lock_time"
    _attr_icon = "mdi:timer-lock"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_native_min_value = 0.0
    _attr_native_max_value = 900.0
    _attr_native_step = 1.0
    _attr_mode = NumberMode.AUTO

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
        return f"{self._key.lockMac}_auto_lock_time"

    @property
    def native_value(self) -> float | None:
        """Return current auto-lock delay in seconds."""
        if self._connection.auto_lock_seconds is not None:
            return float(self._connection.auto_lock_seconds)
        return None

    @property
    def native_min_value(self) -> float:
        """Return min allowed delay, or 0."""
        min_sec = self._connection.auto_lock_limits[0]
        return float(min_sec) if min_sec is not None else 0.0

    @property
    def native_max_value(self) -> float:
        """Return max allowed delay, or 900."""
        max_sec = self._connection.auto_lock_limits[1]
        return float(max_sec) if max_sec is not None else 900.0

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
            self.hass.async_create_task(self._async_fetch_initial_value())

    @callback
    def _on_auto_lock_update(self, seconds: int) -> None:  # noqa: ARG002
        """Update state when auto-lock duration changes."""
        self.async_write_ha_state()

    async def _async_fetch_initial_value(self) -> None:
        """Read initial auto-lock delay from lock."""
        try:
            await self._connection.async_get_auto_lock_info()
        except Exception:  # noqa: BLE001
            pass

    async def async_set_native_value(self, value: float) -> None:
        """Write new auto-lock duration over Bluetooth."""
        try:
            await self._connection.async_set_auto_lock_time(int(value))
        except TTLockError as exc:
            raise HomeAssistantError(
                f"Failed to set auto-lock duration for {self._key.lockMac}: {exc}"
            ) from exc
