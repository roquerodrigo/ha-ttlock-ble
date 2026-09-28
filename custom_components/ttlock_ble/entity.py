"""TtlockBleEntity base class — one device per `VirtualKey`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import (
    CONNECTION_BLUETOOTH,
    ChildDeviceInfo,
    DeviceInfo,
    async_get_device_id_by_identifier,
    format_mac,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, MANUFACTURER
from .coordinator import TtlockBleDataUpdateCoordinator

if TYPE_CHECKING:
    from ttlock_ble import VirtualKey

    from .data import TtlockBleLockState


class TtlockBleEntity(CoordinatorEntity[TtlockBleDataUpdateCoordinator]):
    """Base entity tied to a specific lock (`VirtualKey`)."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
    ) -> None:
        """Bind to the coordinator and the per-lock virtual key."""
        super().__init__(coordinator)
        self._key = key

    @property
    def device_info(self) -> DeviceInfo | ChildDeviceInfo:
        """
        One Home Assistant device per physical lock, keyed by MAC.

        Model, hardware and firmware come from what the lock itself
        reported the last time one was read off it. Until then the model
        falls back to the protocol version carried by the key, which is
        the only thing known about a lock nobody has connected to yet.
        """
        mac = format_mac(self._key.lockMac)
        description = self.coordinator.async_device_description(self._key.lockMac)
        model = None if description is None else description["model"]
        device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            connections={(CONNECTION_BLUETOOTH, mac)},
            name=self._lock_name,
            manufacturer=MANUFACTURER,
            model=model or self._protocol_model,
        )
        if description is None:
            return device_info
        # A key present here is written to the registry device, `None`
        # included, and only a key left out means "leave this alone".
        # Spelling out an unknown version would blank the one a poll
        # stamped on the device before this entity was registered.
        if description["hardware_version"]:
            device_info["hw_version"] = description["hardware_version"]
        if description["firmware_version"]:
            device_info["sw_version"] = description["firmware_version"]
        return device_info

    @property
    def _lock_name(self) -> str:
        """Return the lock's display name: alias, then lock name, then MAC."""
        return self._key.lockAlias or self._key.lockName or self._key.lockMac

    @property
    def _protocol_model(self) -> str:
        """Return the protocol version the key carries, as a model string."""
        return (
            f"Protocol {self._key.lockVersion.protocolType}."
            f"{self._key.lockVersion.protocolVersion}"
        )

    @property
    def _lock_state(self) -> TtlockBleLockState | None:
        """Return the per-lock state snapshot from the coordinator, if any."""
        if self.coordinator.data is None:
            return None  # type: ignore[unreachable]
        return self.coordinator.data.get(self._key.lockMac)


class TtlockBleFingerprintsHubEntity(TtlockBleEntity):
    """The 'Fingerprints' hub device for one lock, parenting a sub-device per print."""

    @property
    def device_info(self) -> DeviceInfo:
        """One hub device per lock, chained under the lock via `via_device_id`."""
        mac = format_mac(self._key.lockMac)
        via_id = async_get_device_id_by_identifier(
            self.hass,
            (DOMAIN, mac),
            config_entry_id=self.coordinator.config_entry.entry_id,
        )
        return DeviceInfo(
            identifiers={(DOMAIN, f"{mac}_fingerprints")},
            via_device_id=via_id,
            name=f"{self._lock_name} Fingerprints",
            manufacturer=MANUFACTURER,
        )


class TtlockBleFingerprintEntity(TtlockBleEntity):
    """One sub-device per enrolled fingerprint, chained under the 'Fingerprints' hub."""

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
        fingerprint_id: bytes,
        slot: int,
    ) -> None:
        """Bind to the coordinator, the lock's key, and this fingerprint's identity."""
        super().__init__(coordinator, key)
        self._fingerprint_id = fingerprint_id
        self._slot = slot

    @property
    def _fingerprint_number(self) -> int:
        """
        The number the official app displays for this enrollment.

        Computed from `fingerprint_id` + `slot` rather than an arbitrary
        index, so it matches the app's own value exactly - shared by
        `device_info`'s name and `TtlockBleFingerprintNumberSensor`'s
        state, rather than each recomputing it slightly differently.
        """
        return int.from_bytes(
            self._fingerprint_id + self._slot.to_bytes(2, "big"), "big"
        )

    @property
    def device_info(self) -> ChildDeviceInfo:
        """
        One child device per enrolled fingerprint, named by its bare number.

        Matches the official app's own display convention: it shows the
        number under the label "Fingerprint Number", never prefixing the
        value itself with the word "Fingerprint".

        A `ChildDeviceInfo` (HA 2026.9+) rather than a regular `DeviceInfo`
        chained through `via_device` - lightweight sub-parts of a device
        are what the devices overview page nests under their parent,
        where a `via_device` link still lists them as loose top-level
        rows. `parent_device_id` needs the hub's registry id, not an
        identifiers tuple, so it is resolved here rather than left for
        the entity platform to do - `via_device`/`via_device_id` do that
        resolution for a regular `DeviceInfo`, `ChildDeviceInfo` does not.

        Resolving it assumes the "Fingerprints" hub device already
        exists, which it does by construction:
        `TtlockBleFingerprintCountSensor` registers it in the same,
        first `async_add_entities` call `async_setup_entry` makes, and
        this entity is only ever created afterward, from the dynamic
        listener - never in that same initial batch.
        """
        mac = format_mac(self._key.lockMac)
        unique = f"{mac}_fp_{self._fingerprint_id.hex()}_{self._slot}"
        parent_id = async_get_device_id_by_identifier(
            self.hass,
            (DOMAIN, f"{mac}_fingerprints"),
            config_entry_id=self.coordinator.config_entry.entry_id,
        )
        return ChildDeviceInfo(
            identifiers={(DOMAIN, unique)},
            parent_device_id=parent_id,
            name=str(self._fingerprint_number),
        )
