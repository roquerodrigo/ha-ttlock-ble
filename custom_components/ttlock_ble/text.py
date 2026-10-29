"""Text platform for ttlock_ble — naming each enrolled fingerprint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.text import TextEntity
from homeassistant.const import EntityCategory

from .entity import TtlockBleEntity
from .fingerprint_store import async_get_fingerprint_store
from .fingerprint_tracker import TtlockBleFingerprintTracker

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import VirtualKey

    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry, TtlockBleEnrolledFingerprint
    from .fingerprint_store import TtlockBleFingerprintStore


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one name entity per fingerprint the admin keys' locks list."""
    coordinator = entry.runtime_data.coordinator
    store = await async_get_fingerprint_store(hass)

    def _create_name_text(
        key: VirtualKey, fingerprint: TtlockBleEnrolledFingerprint
    ) -> TtlockBleFingerprintNameText:
        return TtlockBleFingerprintNameText(coordinator, key, fingerprint, store)

    TtlockBleFingerprintTracker(
        hass, entry, async_add_entities, _create_name_text
    ).async_start()


class TtlockBleFingerprintNameText(TtlockBleEntity, TextEntity):
    """
    Whose fingerprint this is, as the user names it.

    The lock knows a fingerprint only by the number the official app
    shows, which is what the entity is named after. The value is what
    the log events and the last-unlocked-by sensor report for it, and is
    empty until someone names it.
    """

    _attr_translation_key = "fingerprint_name"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_max = 64

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
        fingerprint: TtlockBleEnrolledFingerprint,
        store: TtlockBleFingerprintStore,
    ) -> None:
        """Bind to the lock, the fingerprint and the store keeping its name."""
        super().__init__(coordinator, key)
        self._fingerprint = fingerprint
        self._store = store
        self._attr_translation_placeholders = {"number": str(fingerprint.number)}

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_fingerprint_{self._fingerprint.token}"

    @property
    def native_value(self) -> str:
        """Return the name given to the fingerprint, empty when it has none."""
        return self._store.name_of(self._key.lockMac, self._fingerprint) or ""

    async def async_set_value(self, value: str) -> None:
        """Name the fingerprint."""
        self._store.async_set_name(self._key.lockMac, self._fingerprint, value)
        self.async_write_ha_state()
