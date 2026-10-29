"""Text platform for ttlock_ble — naming each fingerprint, card and passcode."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.text import TextEntity
from homeassistant.const import EntityCategory

from .credential_store import async_get_credential_store
from .credential_tracker import TtlockBleCredentialTracker
from .credential_type import TtlockBleCredentialType
from .entity import TtlockBleEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import VirtualKey

    from .coordinator import TtlockBleDataUpdateCoordinator
    from .credential_store import TtlockBleCredentialStore
    from .data import TtlockBleConfigEntry, TtlockBleKnownCredential


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one name entity per credential each lock is known to hold."""
    coordinator = entry.runtime_data.coordinator
    store = await async_get_credential_store(hass)

    def _create_name_text(
        key: VirtualKey, credential: TtlockBleKnownCredential
    ) -> TtlockBleCredentialNameText:
        if credential.credential_type is TtlockBleCredentialType.FINGERPRINT:
            return TtlockBleFingerprintNameText(coordinator, key, credential, store)
        if credential.credential_type is TtlockBleCredentialType.CARD:
            return TtlockBleCardNameText(coordinator, key, credential, store)
        return TtlockBlePasscodeNameText(coordinator, key, credential, store)

    TtlockBleCredentialTracker(
        hass, entry, async_add_entities, _create_name_text
    ).async_start()


class TtlockBleCredentialNameText(TtlockBleEntity, TextEntity):
    """
    Whose credential this is, as the user names it.

    The lock knows a credential only by its number or its code, which the
    entity is named after — a passcode by three of its digits only. The
    value is what the log events and the last-unlocked-by sensor report
    for it, and is empty until someone names it.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_max = 64

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
        credential: TtlockBleKnownCredential,
        store: TtlockBleCredentialStore,
    ) -> None:
        """Bind to the lock, the credential and the store keeping its name."""
        super().__init__(coordinator, key)
        self._credential = credential
        self._store = store
        self._attr_translation_placeholders = {"label": credential.label}

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return (
            f"{self._key.lockMac}_{self._credential.credential_type}"
            f"_{self._credential.key}"
        )

    @property
    def native_value(self) -> str:
        """Return the name given to the credential, empty when it has none."""
        return (
            self._store.name_of(
                self._key.lockMac,
                self._credential.credential_type,
                self._credential.key,
            )
            or ""
        )

    async def async_set_value(self, value: str) -> None:
        """Name the credential."""
        self._store.async_set_name(
            self._key.lockMac,
            self._credential.credential_type,
            self._credential.key,
            value,
        )
        self.async_write_ha_state()


class TtlockBleFingerprintNameText(TtlockBleCredentialNameText):
    """Whose fingerprint this is, named after the number the app shows."""

    _attr_translation_key = "fingerprint_name"
    _attr_icon = "mdi:fingerprint"


class TtlockBleCardNameText(TtlockBleCredentialNameText):
    """Whose card this is, named after its number."""

    _attr_translation_key = "card_name"
    _attr_icon = "mdi:card-account-details"


class TtlockBlePasscodeNameText(TtlockBleCredentialNameText):
    """Whose passcode this is, named after its first digit and last two."""

    _attr_translation_key = "passcode_name"
    _attr_icon = "mdi:dialpad"
