"""TtlockBleFingerprintTracker — one entity per enrolled fingerprint, kept in step."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.device_registry import (
    async_entries_for_parent_device,
    async_get_device_id_by_identifier,
)
from homeassistant.helpers.device_registry import (
    async_get as async_get_device_registry,
)

from .data import TtlockBleEnrolledFingerprint
from .fingerprint_identifiers import (
    enrolled_fingerprint_of,
    fingerprint_identifier,
    fingerprints_hub_identifier,
)
from .key_privileges import can_administer

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity import Entity
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import FingerprintEntry, VirtualKey

    from .data import TtlockBleConfigEntry


class TtlockBleFingerprintTracker:
    """
    Keeps one entity per fingerprint each lock lists, and none for the rest.

    The fingerprint devices of the last run are rebuilt from the registry
    at setup, so they stay available across a restart instead of waiting
    for a session. Each list the coordinator reads then adds what is new
    and removes the device of every fingerprint the lock no longer holds.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: TtlockBleConfigEntry,
        async_add_entities: AddEntitiesCallback,
        create_entity: Callable[[VirtualKey, TtlockBleEnrolledFingerprint], Entity],
    ) -> None:
        """Bind to the entry whose locks are tracked and the platform's adder."""
        self._hass = hass
        self._entry = entry
        self._async_add_entities = async_add_entities
        self._create_entity = create_entity
        self._tracked: dict[str, set[TtlockBleEnrolledFingerprint]] = {}
        self._synced_lists: dict[str, list[FingerprintEntry]] = {}

    @callback
    def async_start(self) -> None:
        """Restore the last run's fingerprints and follow the coordinator."""
        coordinator = self._entry.runtime_data.coordinator
        self._async_restore()
        self._entry.async_on_unload(coordinator.async_add_listener(self._async_sync))
        self._async_sync()

    @property
    def _admin_keys(self) -> list[VirtualKey]:
        return [
            key for key in self._entry.runtime_data.virtual_keys if can_administer(key)
        ]

    @callback
    def _async_restore(self) -> None:
        device_registry = async_get_device_registry(self._hass)
        entities: list[Entity] = []
        for key in self._admin_keys:
            hub_id = async_get_device_id_by_identifier(
                self._hass,
                fingerprints_hub_identifier(key.lockMac),
                config_entry_id=self._entry.entry_id,
            )
            tracked = self._tracked.setdefault(key.lockMac, set())
            for child in async_entries_for_parent_device(device_registry, hub_id):
                fingerprint = enrolled_fingerprint_of(child.identifiers, key.lockMac)
                if fingerprint is None:
                    continue
                tracked.add(fingerprint)
                entities.append(self._create_entity(key, fingerprint))
        if entities:
            self._async_add_entities(entities)

    @callback
    def _async_sync(self) -> None:
        coordinator = self._entry.runtime_data.coordinator
        entities: list[Entity] = []
        for key in self._admin_keys:
            entries = coordinator.async_fingerprints(key.lockMac)
            if entries is None or entries is self._synced_lists.get(key.lockMac):
                continue
            self._synced_lists[key.lockMac] = entries
            enrolled = {TtlockBleEnrolledFingerprint.from_entry(e) for e in entries}
            tracked = self._tracked.get(key.lockMac, set())
            for fingerprint in tracked - enrolled:
                self._async_remove_device(key, fingerprint)
            entities.extend(
                self._create_entity(key, fingerprint)
                for fingerprint in sorted(enrolled - tracked, key=lambda f: f.number)
            )
            self._tracked[key.lockMac] = enrolled
        if entities:
            self._async_add_entities(entities)

    @callback
    def _async_remove_device(
        self, key: VirtualKey, fingerprint: TtlockBleEnrolledFingerprint
    ) -> None:
        device_registry = async_get_device_registry(self._hass)
        device = device_registry.async_get_child_device_by_identifier(
            fingerprint_identifier(key.lockMac, fingerprint), self._entry.entry_id
        )
        if device is not None:
            device_registry.async_remove_device(device.id)
