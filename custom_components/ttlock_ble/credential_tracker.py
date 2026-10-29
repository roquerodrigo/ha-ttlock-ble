"""TtlockBleCredentialTracker — one name entity per known credential, kept in step."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.entity_registry import (
    async_get as async_get_entity_registry,
)

from .const import DOMAIN
from .credential_type import TtlockBleCredentialType
from .key_privileges import can_administer

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import VirtualKey

    from .data import TtlockBleConfigEntry, TtlockBleKnownCredential
    from .text import TtlockBleCredentialNameText

# Lists only an admin key can read. Passcodes are also learned from the
# operation log, which every key reads.
ADMIN_LISTED_CREDENTIAL_TYPES: frozenset[TtlockBleCredentialType] = frozenset(
    {TtlockBleCredentialType.FINGERPRINT, TtlockBleCredentialType.CARD}
)

TRACKED_CREDENTIAL_TYPES: tuple[TtlockBleCredentialType, ...] = (
    TtlockBleCredentialType.FINGERPRINT,
    TtlockBleCredentialType.CARD,
    TtlockBleCredentialType.PASSCODE,
)


class TtlockBleCredentialTracker:
    """
    Keeps one entity per credential each lock is known to hold, and no more.

    The credential store holds what each lock held last, so the entities
    of the last run come back at setup without a session. Every change
    the coordinator announces after that adds the credentials that are
    new and removes the entity of each one the lock no longer holds.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: TtlockBleConfigEntry,
        async_add_entities: AddEntitiesCallback,
        create_entity: Callable[
            [VirtualKey, TtlockBleKnownCredential], TtlockBleCredentialNameText
        ],
    ) -> None:
        """Bind to the entry whose locks are tracked and the platform's adder."""
        self._hass = hass
        self._entry = entry
        self._async_add_entities = async_add_entities
        self._create_entity = create_entity
        self._tracked: dict[tuple[str, TtlockBleCredentialType], dict[str, str]] = {}

    @callback
    def async_start(self) -> None:
        """Create the stored credentials' entities and follow the coordinator."""
        coordinator = self._entry.runtime_data.coordinator
        self._entry.async_on_unload(coordinator.async_add_listener(self._async_sync))
        self._async_sync()

    @callback
    def _async_sync(self) -> None:
        coordinator = self._entry.runtime_data.coordinator
        entities: list[TtlockBleCredentialNameText] = []
        for key in self._entry.runtime_data.virtual_keys:
            for credential_type in TRACKED_CREDENTIAL_TYPES:
                if credential_type in ADMIN_LISTED_CREDENTIAL_TYPES and not (
                    can_administer(key)
                ):
                    continue
                known = coordinator.async_credentials(key.lockMac, credential_type)
                current = {credential.key: credential for credential in known or []}
                tracked = self._tracked.setdefault((key.lockMac, credential_type), {})
                for credential_key in set(tracked) - set(current):
                    self._async_remove_entity(tracked.pop(credential_key))
                for credential_key, credential in current.items():
                    if credential_key in tracked:
                        continue
                    entity = self._create_entity(key, credential)
                    tracked[credential_key] = entity.unique_id
                    entities.append(entity)
        if entities:
            self._async_add_entities(entities)

    @callback
    def _async_remove_entity(self, unique_id: str) -> None:
        entity_registry = async_get_entity_registry(self._hass)
        entity_id = entity_registry.async_get_entity_id("text", DOMAIN, unique_id)
        if entity_id is not None:
            entity_registry.async_remove(entity_id)
