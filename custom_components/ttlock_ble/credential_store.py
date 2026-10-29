"""Persisted credentials each lock holds and the names given to them."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.singleton import singleton
from homeassistant.helpers.storage import Store
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN
from .data import TtlockBleKnownCredential

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .credential_type import TtlockBleCredentialType
    from .data import TtlockBleStoredCredential

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.credentials"
SAVE_DELAY_SECONDS = 10

type _StoredLock = dict[str, dict[str, TtlockBleStoredCredential]]


class TtlockBleCredentialStore:
    """
    The credentials each lock is known to hold, and whose each one is.

    The lock knows a credential only by its number or its code, so the
    person it belongs to is something only the user can say, and it has
    to outlive a restart. Keeping what each lock holds next to the names
    is what lets the name entities come back at setup without a session,
    and lets a credential the lock dropped take its name with it.

    Keyed by MAC rather than by entry, so a lock keeps its names across a
    reconfigure. An empty name stands for a credential nobody named yet.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Bind the store to HA's storage helper."""
        self._store: Store[dict[str, _StoredLock]] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
        )
        self._locks: dict[str, _StoredLock] = {}

    async def async_load(self) -> None:
        """Read the persisted credentials, tolerating a missing or empty file."""
        data = await self._store.async_load()
        if not data:
            return
        self._locks = data

    def known(
        self, mac: str, credential_type: TtlockBleCredentialType
    ) -> list[TtlockBleKnownCredential] | None:
        """Return the credentials of a type `mac` holds, or `None` before any."""
        stored = self._locks.get(mac, {}).get(credential_type)
        if stored is None:
            return None
        return sorted(
            (
                TtlockBleKnownCredential(credential_type, key, credential["label"])
                for key, credential in stored.items()
            ),
            key=_display_order,
        )

    def name_of(
        self, mac: str, credential_type: TtlockBleCredentialType, key: str
    ) -> str | None:
        """Return the name given to a credential, or `None` when it has none."""
        credential = self._credentials(mac, credential_type).get(key)
        return (credential and credential["name"]) or None

    def label_of(
        self, mac: str, credential_type: TtlockBleCredentialType, key: str
    ) -> str | None:
        """Return the label a known credential is shown with."""
        credential = self._credentials(mac, credential_type).get(key)
        return credential["label"] if credential else None

    def async_set_name(
        self, mac: str, credential_type: TtlockBleCredentialType, key: str, name: str
    ) -> None:
        """Name a known credential; an empty name clears the one it had."""
        credential = self._credentials(mac, credential_type).get(key)
        if credential is None:
            return
        credential["name"] = name.strip()
        self._async_save()

    def async_replace(
        self,
        mac: str,
        credential_type: TtlockBleCredentialType,
        credentials: list[TtlockBleKnownCredential],
    ) -> None:
        """Adopt a complete list the lock just read, keeping the names still held."""
        previous = self._locks.get(mac, {}).get(credential_type)
        current: dict[str, TtlockBleStoredCredential] = {
            credential.key: {
                "label": credential.label,
                "name": (previous or {}).get(credential.key, {"name": ""})["name"],
            }
            for credential in credentials
        }
        if current == previous:
            return
        self._locks.setdefault(mac, {})[credential_type] = current
        self._async_save()

    def async_add(self, mac: str, credential: TtlockBleKnownCredential) -> bool:
        """Remember a credential seen on `mac`. Reports whether it was new."""
        stored = self._locks.setdefault(mac, {}).setdefault(
            credential.credential_type, {}
        )
        if credential.key in stored:
            return False
        stored[credential.key] = {
            "label": _unique_label(credential.label, stored),
            "name": "",
        }
        self._async_save()
        return True

    def async_rekey(
        self,
        mac: str,
        previous: TtlockBleKnownCredential,
        current: TtlockBleKnownCredential,
    ) -> bool:
        """Move a changed credential to its new key, keeping its name."""
        stored = self._credentials(mac, previous.credential_type)
        name = stored.pop(previous.key, {"label": "", "name": ""})["name"]
        added = self.async_add(mac, current)
        if name:
            self._credentials(mac, current.credential_type)[current.key]["name"] = name
        self._async_save()
        return added

    def async_remove(self, mac: str, credential: TtlockBleKnownCredential) -> bool:
        """Forget a credential the lock dropped. Reports whether it was known."""
        stored = self._credentials(mac, credential.credential_type)
        if stored.pop(credential.key, None) is None:
            return False
        self._async_save()
        return True

    def async_clear(self, mac: str, credential_type: TtlockBleCredentialType) -> bool:
        """Forget every credential of a type on `mac`. Reports whether any was."""
        stored = self._credentials(mac, credential_type)
        if not stored:
            return False
        stored.clear()
        self._async_save()
        return True

    def _credentials(
        self, mac: str, credential_type: TtlockBleCredentialType
    ) -> dict[str, TtlockBleStoredCredential]:
        return self._locks.get(mac, {}).get(credential_type, {})

    def _async_save(self) -> None:
        self._store.async_delay_save(self._snapshot, SAVE_DELAY_SECONDS)

    def _snapshot(self) -> dict[str, _StoredLock]:
        """Render the in-memory credentials as the JSON the store writes."""
        return {
            mac: {
                credential_type: {
                    key: {"label": value["label"], "name": value["name"]}
                    for key, value in stored.items()
                }
                for credential_type, stored in by_type.items()
            }
            for mac, by_type in self._locks.items()
        }


def _display_order(credential: TtlockBleKnownCredential) -> tuple[int, int, str]:
    if credential.label.isdigit():
        return (0, int(credential.label), "")
    return (1, 0, credential.label)


def _unique_label(label: str, stored: dict[str, TtlockBleStoredCredential]) -> str:
    """Tell apart two passcodes whose visible digits are the same."""
    taken = {credential["label"] for credential in stored.values()}
    if label not in taken:
        return label
    suffix = 2
    while f"{label} #{suffix}" in taken:
        suffix += 1
    return f"{label} #{suffix}"


STORE_KEY: HassKey[TtlockBleCredentialStore] = HassKey(f"{DOMAIN}_credential_store")


@singleton(STORE_KEY, async_=True)
async def async_get_credential_store(hass: HomeAssistant) -> TtlockBleCredentialStore:
    """
    Return the one store this Home Assistant instance shares.

    The file is keyed by MAC and holds every lock of every entry, so one
    instance per entry would let the last one to write drop the names
    another entry had saved in the meantime.
    """
    store = TtlockBleCredentialStore(hass)
    await store.async_load()
    return store
