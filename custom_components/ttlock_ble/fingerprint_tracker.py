"""TtlockBleFingerprintTracker — one entity per enrolled fingerprint, kept in step."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.entity_registry import (
    async_get as async_get_entity_registry,
)

from .const import DOMAIN
from .key_privileges import can_administer

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import VirtualKey

    from .data import TtlockBleConfigEntry, TtlockBleEnrolledFingerprint
    from .text import TtlockBleFingerprintNameText


class TtlockBleFingerprintTracker:
    """
    Keeps one entity per fingerprint each lock lists, and none for the rest.

    The fingerprint store holds the list each lock last answered, so the
    entities of the last run come back at setup without a session. Every
    list the coordinator reads after that adds the fingerprints that are
    new and removes the entity of each one the lock no longer holds.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: TtlockBleConfigEntry,
        async_add_entities: AddEntitiesCallback,
        create_entity: Callable[
            [VirtualKey, TtlockBleEnrolledFingerprint], TtlockBleFingerprintNameText
        ],
    ) -> None:
        """Bind to the entry whose locks are tracked and the platform's adder."""
        self._hass = hass
        self._entry = entry
        self._async_add_entities = async_add_entities
        self._create_entity = create_entity
        self._tracked: dict[str, dict[TtlockBleEnrolledFingerprint, str]] = {}

    @callback
    def async_start(self) -> None:
        """Create the stored fingerprints' entities and follow the coordinator."""
        coordinator = self._entry.runtime_data.coordinator
        self._entry.async_on_unload(coordinator.async_add_listener(self._async_sync))
        self._async_sync()

    @callback
    def _async_sync(self) -> None:
        coordinator = self._entry.runtime_data.coordinator
        entities: list[TtlockBleFingerprintNameText] = []
        for key in self._entry.runtime_data.virtual_keys:
            if not can_administer(key):
                continue
            enrolled = set(coordinator.async_fingerprints(key.lockMac) or [])
            tracked = self._tracked.setdefault(key.lockMac, {})
            for fingerprint in set(tracked) - enrolled:
                self._async_remove_entity(tracked.pop(fingerprint))
            for fingerprint in sorted(
                enrolled - set(tracked), key=lambda fingerprint: fingerprint.number
            ):
                entity = self._create_entity(key, fingerprint)
                tracked[fingerprint] = entity.unique_id
                entities.append(entity)
        if entities:
            self._async_add_entities(entities)

    @callback
    def _async_remove_entity(self, unique_id: str) -> None:
        entity_registry = async_get_entity_registry(self._hass)
        entity_id = entity_registry.async_get_entity_id("text", DOMAIN, unique_id)
        if entity_id is not None:
            entity_registry.async_remove(entity_id)
