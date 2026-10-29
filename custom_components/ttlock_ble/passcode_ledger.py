"""TtlockBlePasscodeLedger — the passcodes each lock holds, as its log tells."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from ttlock_ble import LogOperate

from .connection import log_signal
from .credential_type import TtlockBleCredentialType
from .data import TtlockBleKnownCredential

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import CALLBACK_TYPE, HomeAssistant

    from ttlock_ble import LogEntry, VirtualKey

    from .coordinator import TtlockBleDataUpdateCoordinator
    from .credential_store import TtlockBleCredentialStore

# Records made with a passcode the lock accepted, or right after adding one.
# A rejected code is left out: it is not a passcode the lock holds.
ACCEPTED_PASSCODE_RECORD_TYPES: frozenset[int] = frozenset(
    {
        LogOperate.KEYBOARD_PASSWORD_UNLOCK,
        LogOperate.PASSCODE_LOCK,
        LogOperate.PASSCODE_UNLOCK_FAILED_LOCK_REVERSE,
        LogOperate.DOUBLE_CHECK_PASSCODE_UNLOCK,
        LogOperate.ADMIN_CODE_UNLOCK,
        LogOperate.ADD_PASSCODE_SUCCESSFULLY,
    },
)

# Records naming a passcode the lock no longer accepts.
DROPPED_PASSCODE_RECORD_TYPES: frozenset[int] = frozenset(
    {
        LogOperate.KEYBOARD_REMOVE_SINGLE_PASSWORD,
        LogOperate.KEYBOARD_PASSWORD_KICKED,
        LogOperate.PASSCODE_EXPIRED,
        LogOperate.PASSCODE_IN_BLACK_LIST,
    },
)


class TtlockBlePasscodeLedger:
    """
    Keeps the known passcodes of each lock in step with its operation log.

    The lock cannot list every passcode it holds: one the official app
    generated offline stays out of the list until it is used. Its log is
    complete instead, and names the code on every use, change, deletion
    and expiry, so it is what passcodes are learned from and forgotten by.
    A changed code keeps the name the old one had.

    It follows each log twice. Passcodes are learned before the platforms
    see a record, so the record that introduces one is already shown with
    its label; they are changed and forgotten after, so the record that
    deletes or changes one still shows whose it was.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        store: TtlockBleCredentialStore,
        coordinator: TtlockBleDataUpdateCoordinator,
    ) -> None:
        """Bind to the store the passcodes are kept in."""
        self._hass = hass
        self._store = store
        self._coordinator = coordinator

    @callback
    def async_track_learning(
        self, virtual_keys: list[VirtualKey]
    ) -> list[CALLBACK_TYPE]:
        """Learn passcodes from every lock's log; return the unsubscribers."""
        return self._async_follow(virtual_keys, self._async_learn)

    @callback
    def async_track_forgetting(
        self, virtual_keys: list[VirtualKey]
    ) -> list[CALLBACK_TYPE]:
        """Change and forget passcodes per log record; return the unsubscribers."""
        return self._async_follow(virtual_keys, self._async_forget)

    @callback
    def _async_follow(
        self,
        virtual_keys: list[VirtualKey],
        apply: Callable[[str, LogEntry], bool],
    ) -> list[CALLBACK_TYPE]:
        return [
            async_dispatcher_connect(
                self._hass,
                log_signal(key.lockMac),
                partial(self._async_note, apply, key.lockMac),
            )
            for key in virtual_keys
        ]

    @callback
    def _async_note(
        self, apply: Callable[[str, LogEntry], bool], mac: str, record: LogEntry
    ) -> None:
        if apply(mac, record):
            self._coordinator.async_update_listeners()

    def _async_learn(self, mac: str, record: LogEntry) -> bool:
        if record.record_type not in ACCEPTED_PASSCODE_RECORD_TYPES:
            return False
        if not record.password:
            return False
        return self._store.async_add(
            mac, TtlockBleKnownCredential.from_passcode(mac, record.password)
        )

    def _async_forget(self, mac: str, record: LogEntry) -> bool:
        if record.record_type == LogOperate.KEYBOARD_REMOVE_ALL_PASSWORDS:
            return self._store.async_clear(mac, TtlockBleCredentialType.PASSCODE)
        if not record.password:
            return False
        credential = TtlockBleKnownCredential.from_passcode(mac, record.password)
        if record.record_type in DROPPED_PASSCODE_RECORD_TYPES:
            return self._store.async_remove(mac, credential)
        if record.record_type == LogOperate.KEYBOARD_MODIFY_PASSWORD:
            return self._async_change(mac, credential, record.new_password)
        return False

    def _async_change(
        self,
        mac: str,
        credential: TtlockBleKnownCredential,
        new_passcode: str | None,
    ) -> bool:
        if not new_passcode:
            return False
        replacement = TtlockBleKnownCredential.from_passcode(mac, new_passcode)
        self._store.async_rekey(mac, credential, replacement)
        return True
