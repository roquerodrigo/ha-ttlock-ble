"""Button platform for ttlock_ble — manual actions for clock, log, and state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from ttlock_ble import TTLockError

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
    """Create action buttons for each VirtualKey."""
    data = entry.runtime_data
    entities: list[ButtonEntity] = []

    for key in data.virtual_keys:
        connection = data.connections[key.lockMac]
        entities.append(
            TtlockBleSyncClockButton(data.coordinator, key, connection)
        )
        entities.append(
            TtlockBleSyncLogButton(data.coordinator, key, connection)
        )
        entities.append(
            TtlockBleRefreshStateButton(data.coordinator, key, connection)
        )
        entities.append(
            TtlockBleSyncPasscodesButton(data.coordinator, key, connection)
        )
        entities.append(
            TtlockBleSyncCardsButton(data.coordinator, key, connection)
        )
        entities.append(
            TtlockBleSyncFingerprintsButton(data.coordinator, key, connection)
        )
        entities.append(
            TtlockBleSyncPassageModeButton(data.coordinator, key, connection)
        )

    async_add_entities(entities)


class TtlockBleButtonEntity(TtlockBleEntity, ButtonEntity):
    """Base button entity for TTLock BLE."""

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
        connection: TtlockBleConnection,
    ) -> None:
        """Bind entity to coordinator and connection."""
        super().__init__(coordinator, key)
        self._connection = connection


class TtlockBleSyncClockButton(TtlockBleButtonEntity):
    """Calibrate the lock's hardware clock to Home Assistant local time."""

    _attr_translation_key = "sync_clock"
    _attr_icon = "mdi:clock-sync"
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def unique_id(self) -> str:
        """Return a stable unique id."""
        return f"{self._key.lockMac}_sync_clock"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.coordinator.async_sync_clock_now(self._connection)
        except TTLockError as exc:
            raise HomeAssistantError(
                f"Failed to synchronize clock for {self._key.lockMac}: {exc}"
            ) from exc


class TtlockBleSyncLogButton(TtlockBleButtonEntity):
    """Pull unread on-chip operation records from the lock."""

    _attr_translation_key = "sync_log"
    _attr_icon = "mdi:history"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return a stable unique id."""
        return f"{self._key.lockMac}_sync_log"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._connection.async_get_operation_log()
        except TTLockError as exc:
            raise HomeAssistantError(
                f"Failed to sync operation log for {self._key.lockMac}: {exc}"
            ) from exc


class TtlockBleRefreshStateButton(TtlockBleButtonEntity):
    """Force an immediate Bluetooth query to update lock state and battery."""

    _attr_translation_key = "refresh_state"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return a stable unique id."""
        return f"{self._key.lockMac}_refresh_state"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.coordinator.async_poll_lock(self._connection)
        except TTLockError as exc:
            raise HomeAssistantError(
                f"Failed to refresh state for {self._key.lockMac}: {exc}"
            ) from exc


class TtlockBleSyncPasscodesButton(TtlockBleButtonEntity):
    """Query passcodes from the lock and refresh the passcodes count."""

    _attr_translation_key = "sync_passcodes"
    _attr_icon = "mdi:form-textbox-password"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return a stable unique id."""
        return f"{self._key.lockMac}_sync_passcodes"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._connection.async_get_passcodes()
        except TTLockError as exc:
            raise HomeAssistantError(
                f"Failed to sync passcodes for {self._key.lockMac}: {exc}"
            ) from exc


class TtlockBleSyncCardsButton(TtlockBleButtonEntity):
    """Query IC cards from the lock and refresh the cards count."""

    _attr_translation_key = "sync_cards"
    _attr_icon = "mdi:smart-card-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return a stable unique id."""
        return f"{self._key.lockMac}_sync_cards"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._connection.async_get_cards()
        except TTLockError as exc:
            raise HomeAssistantError(
                f"Failed to sync cards for {self._key.lockMac}: {exc}"
            ) from exc


class TtlockBleSyncFingerprintsButton(TtlockBleButtonEntity):
    """Query fingerprints from the lock and refresh the fingerprints count."""

    _attr_translation_key = "sync_fingerprints"
    _attr_icon = "mdi:fingerprint"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return a stable unique id."""
        return f"{self._key.lockMac}_sync_fingerprints"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._connection.async_get_fingerprints()
        except TTLockError as exc:
            raise HomeAssistantError(
                f"Failed to sync fingerprints for {self._key.lockMac}: {exc}"
            ) from exc


class TtlockBleSyncPassageModeButton(TtlockBleButtonEntity):
    """Query passage mode schedules from the lock and refresh the status and sensors."""

    _attr_translation_key = "sync_passage_mode"
    _attr_icon = "mdi:calendar-sync"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return a stable unique id."""
        return f"{self._key.lockMac}_sync_passage_mode"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._connection.async_get_passage_mode()
        except TTLockError as exc:
            raise HomeAssistantError(
                f"Failed to sync passage mode for {self._key.lockMac}: {exc}"
            ) from exc
