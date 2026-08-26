"""Passive advertisement tracking for ttlock_ble."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
    async_register_callback,
)
from homeassistant.core import callback
from homeassistant.helpers.device_registry import format_mac

from ttlock_ble import LockAdvertisement

from .const import LOGGER

if TYPE_CHECKING:
    from homeassistant.components.bluetooth import (
        BluetoothChange,
        BluetoothServiceInfoBleak,
    )
    from homeassistant.core import CALLBACK_TYPE, HomeAssistant

    from ttlock_ble import VirtualKey

    from .coordinator import TtlockBleDataUpdateCoordinator


class TtlockBleAdvertisementTracker:
    """
    Keep lock state fresh from the advertisements HA's bluetooth manager sees.

    The firmware publishes the bolt position and the battery level in the
    manufacturer data of every advertisement, so tracking them costs no
    BLE session at all. This is the only channel that reports an
    out-of-band change — auto-lock, the official app, a keypad code —
    once the lock has dropped the connection it pushes events on, which
    it does within seconds of going idle.

    Nothing here opens a session, and nothing falls back to one. A
    dormant lock advertises without a usable bolt position, so those
    frames carry only battery and the entity keeps reporting whatever
    was last known — `unknown`, if the lock has not been awake since
    Home Assistant started. That is the honest answer: the bolt position
    is not something anyone knows until the lock says so.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: TtlockBleDataUpdateCoordinator,
    ) -> None:
        """Bind the tracker to the coordinator it feeds."""
        self._hass = hass
        self._coordinator = coordinator

    @callback
    def async_register(self, virtual_keys: list[VirtualKey]) -> list[CALLBACK_TYPE]:
        """Subscribe to each lock's advertisements; return the unsubscribe callables."""
        return [
            async_register_callback(
                self._hass,
                partial(self._async_on_advertisement, key.lockMac),
                BluetoothCallbackMatcher(address=key.lockMac, connectable=False),
                BluetoothScanningMode.ACTIVE,
            )
            for key in virtual_keys
        ]

    @callback
    def _async_on_advertisement(
        self,
        mac: str,
        service_info: BluetoothServiceInfoBleak,
        _change: BluetoothChange,
    ) -> None:
        """Publish whatever the advertisement carries, and nothing more."""
        advertisement = self._decode(mac, service_info)
        if advertisement is not None:
            self._coordinator.async_apply_advertisement(mac, advertisement)
            return
        LOGGER.debug(
            "No state in the advertisement for %s (%s)",
            mac,
            {
                company_id: payload.hex()
                for company_id, payload in service_info.manufacturer_data.items()
            },
        )

    def _decode(
        self,
        mac: str,
        service_info: BluetoothServiceInfoBleak,
    ) -> LockAdvertisement | None:
        """
        Return the entry of `manufacturer_data` that decodes as this lock's state.

        The address the advertisement carries has to match the lock we
        expect: a payload long enough to decode is not proof that it is a
        TTLock payload, and the trailing address is the only field with a
        value we can check independently.
        """
        expected = format_mac(mac)
        for company_id, payload in service_info.manufacturer_data.items():
            advertisement = LockAdvertisement.from_manufacturer_data(
                company_id,
                payload,
            )
            if advertisement is None:
                continue
            if format_mac(advertisement.lock_mac) == expected:
                return advertisement
            LOGGER.debug(
                "Ignoring advertisement for %s: decoded address %s does not match (%s)",
                mac,
                advertisement.lock_mac,
                payload.hex(),
            )
        return None
