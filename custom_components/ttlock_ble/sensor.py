"""Sensor platform for ttlock_ble — lock health, credentials and the last unlock."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.components.bluetooth import (
    MONOTONIC_TIME,
    async_last_service_info,
)
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from ttlock_ble import LockFeature, LogOperate

from .connection import event_signal, log_signal
from .credential_resolver import TtlockBleCredentialResolver
from .credential_store import async_get_credential_store
from .credential_type import TtlockBleCredentialType
from .entity import TtlockBleEntity
from .event import UNLOCK_RECORD_TYPES
from .key_privileges import can_administer, may_hold

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from ttlock_ble import LockEvent, LogEntry, VirtualKey

    from .coordinator import TtlockBleDataUpdateCoordinator
    from .data import TtlockBleConfigEntry, TtlockBleLastUnlockAttributes

# How often the recorded advertisement time is re-read. Costs nothing on
# the wire: it only looks at what the bluetooth manager already holds.
LAST_SEEN_REFRESH_INTERVAL = timedelta(seconds=30)

# Unlock records that name who unlocked. A door sensor reporting the door
# open is filed as an unlock too, but it follows the unlock that opened
# it, and would otherwise replace whoever that was with nobody.
CREDENTIAL_UNLOCK_RECORD_TYPES: frozenset[int] = UNLOCK_RECORD_TYPES - {
    LogOperate.DOOR_SENSOR_UNLOCK
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TtlockBleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the per-lock sensors."""
    data = entry.runtime_data
    resolver = TtlockBleCredentialResolver(await async_get_credential_store(hass))
    async_add_entities(
        sensor
        for key in data.virtual_keys
        for sensor in (
            TtlockBleBatterySensor(data.coordinator, key),
            TtlockBleLastSeenSensor(data.coordinator, key),
            TtlockBleClockDriftSensor(data.coordinator, key),
            TtlockBleLastUnlockedBySensor(data.coordinator, key, resolver),
            *(
                (TtlockBleFingerprintCountSensor(data.coordinator, key),)
                if can_administer(key) and may_hold(key, LockFeature.FINGER_PRINT)
                else ()
            ),
            *(
                (TtlockBleCardCountSensor(data.coordinator, key),)
                if can_administer(key) and may_hold(key, LockFeature.IC)
                else ()
            ),
        )
    )


class TtlockBleBatterySensor(TtlockBleEntity, SensorEntity):
    """Battery level reported by the lock — refreshed on poll and on every push."""

    _attr_translation_key = "battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
    ) -> None:
        """Bind the sensor to its key + coordinator."""
        super().__init__(coordinator, key)
        self._attr_native_value: int | None = None
        self._sync_from_coordinator()

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_battery"

    async def async_added_to_hass(self) -> None:
        """Subscribe to push-event notifications for the lock's MAC."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                event_signal(self._key.lockMac),
                self._on_lock_event,
            ),
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Adopt the coordinator's freshest battery reading, if any."""
        self._sync_from_coordinator()
        super()._handle_coordinator_update()

    @callback
    def _on_lock_event(self, event: LockEvent) -> None:
        """Adopt the battery byte the lock embedded in its push payload."""
        if event.battery is None:
            return
        self._attr_native_value = event.battery
        self.async_write_ha_state()

    def _sync_from_coordinator(self) -> None:
        """Copy `battery_level` from the coordinator snapshot, if known."""
        state = self._lock_state
        if state is None:
            return
        battery = state.get("battery_level")
        if battery is None:
            return
        self._attr_native_value = battery


class TtlockBleClockDriftSensor(TtlockBleEntity, SensorEntity):
    """
    How far the lock's own clock was off local time when last compared.

    The lock stamps every operation-log record from a clock it keeps
    itself, with no NTP and no offset attached, and Home Assistant reads
    those stamps as local time. A drifted clock therefore files a whole
    day of door events at the wrong hour, and nothing else on the device
    would show it.

    Positive means the lock runs ahead. The value is what was measured
    before any correction, so it stays a reading of how far the clock
    wanders rather than resetting to zero every time one is written
    back. It reports `unknown` until a session opened for something else
    has carried a comparison — nothing here connects for it.
    """

    _attr_translation_key = "clock_drift"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 1

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_clock_drift"

    @property
    def native_value(self) -> float | None:
        """Return the drift of the last comparison, if one has run."""
        sync = self.coordinator.async_clock_sync(self._key.lockMac)
        return None if sync is None else sync["drift_seconds"]

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Carry when the comparison ran, so a stale reading reads as stale."""
        sync = self.coordinator.async_clock_sync(self._key.lockMac)
        return None if sync is None else {"checked_at": sync["checked_at"]}


class TtlockBleLastSeenSensor(TtlockBleEntity, SensorEntity):
    """
    When Home Assistant last received an advertisement from the lock.

    A lock that is working normally is silent most of the time: it holds
    no connection, and its own advertisements are the only sign it is
    still there. This reports the freshness of that sign, which is what
    separates "idle" from "out of range" — a distinction the connection
    sensor cannot make, because the session is down in both cases.

    The value is read from the bluetooth manager's own history rather
    than from the advertisement callback, because that callback is not
    told about an advertisement whose payload matches the previous one.
    An idle lock repeats the same bytes for as long as nothing about it
    changes, so a sensor driven by the callback stops moving while the
    lock is in perfect health — which is precisely backwards.

    Nothing announces those recorded-but-undispatched advertisements, so
    the value is re-read on a timer. The timer is this entity's own and
    not `should_poll`: on a `CoordinatorEntity` polling means
    `async_request_refresh`, which opens a BLE session to the lock. That
    turned a passive read of local memory into a connection every
    refresh interval, against a lock whose polling is deliberately
    spaced by `scan_interval`.
    """

    _attr_translation_key = "last_seen"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:bluetooth-audio"

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
    ) -> None:
        """Bind the sensor to its key + coordinator."""
        super().__init__(coordinator, key)
        self._reported_at: float | None = None
        self._attr_native_value: datetime | None = None

    async def async_added_to_hass(self) -> None:
        """Re-read the history on a timer of its own."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self._async_reread_history,
                LAST_SEEN_REFRESH_INTERVAL,
            ),
        )

    @callback
    def _async_reread_history(self, _now: datetime) -> None:
        """Publish whatever the bluetooth manager has recorded since."""
        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_last_seen"

    @property
    def native_value(self) -> datetime | None:
        """
        Return when the last advertisement arrived, as a wall-clock time.

        The stored reception time is monotonic, so it is converted on
        read and then cached against it: recomputing on every poll would
        walk the timestamp by a fraction of a second each time and write
        a new state for an advertisement that never changed.
        """
        service_info = async_last_service_info(
            self.hass,
            self._key.lockMac,
            connectable=False,
        )
        if service_info is None:
            return self._attr_native_value
        if service_info.time != self._reported_at:
            self._reported_at = service_info.time
            age = MONOTONIC_TIME() - service_info.time
            self._attr_native_value = dt_util.utcnow() - timedelta(seconds=age)
        return self._attr_native_value


class TtlockBleFingerprintCountSensor(TtlockBleEntity, SensorEntity):
    """How many fingerprints the lock lists, as of the last read."""

    _attr_translation_key = "fingerprint_count"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_fingerprint_count"

    @property
    def native_value(self) -> int | None:
        """Return how many fingerprints the last read listed, if any."""
        fingerprints = self.coordinator.async_credentials(
            self._key.lockMac, TtlockBleCredentialType.FINGERPRINT
        )
        return None if fingerprints is None else len(fingerprints)


class TtlockBleCardCountSensor(TtlockBleEntity, SensorEntity):
    """How many cards the lock lists, as of the last read."""

    _attr_translation_key = "card_count"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_card_count"

    @property
    def native_value(self) -> int | None:
        """Return how many cards the last read listed, if any."""
        cards = self.coordinator.async_credentials(
            self._key.lockMac, TtlockBleCredentialType.CARD
        )
        return None if cards is None else len(cards)


class TtlockBleLastUnlockedBySensor(TtlockBleEntity, RestoreSensor):
    """
    Who last unlocked the lock, as its operation log tells it.

    The state is the name of the credential when one is known — a named
    fingerprint, card or passcode, or `Home Assistant` for an unlock sent
    by this integration — and otherwise its identifier: the number of a
    fingerprint or card nobody named yet, or the masked label of a
    passcode. Anything else reads `unknown`, with `credential_type`
    saying what was used.

    Records reach this in the order they are read, and a read can carry
    several, so one older than the unlock already shown is ignored.
    """

    _attr_translation_key = "last_unlocked_by"
    _attr_icon = "mdi:account-key"

    def __init__(
        self,
        coordinator: TtlockBleDataUpdateCoordinator,
        key: VirtualKey,
        resolver: TtlockBleCredentialResolver,
    ) -> None:
        """Bind to the lock and to what names the credentials of its records."""
        super().__init__(coordinator, key)
        self._resolver = resolver
        self._attr_native_value: str | None = None
        self._unlock_attributes: TtlockBleLastUnlockAttributes = {}
        self._unlocked_at: datetime | None = None

    @property
    def unique_id(self) -> str:
        """Return a stable unique id for this entity."""
        return f"{self._key.lockMac}_last_unlocked_by"

    @property
    def extra_state_attributes(self) -> TtlockBleLastUnlockAttributes:
        """Carry the credential's type and identifier, and when it unlocked."""
        return self._unlock_attributes

    async def async_added_to_hass(self) -> None:
        """Bring back the last unlock, then follow the operation log."""
        await super().async_added_to_hass()
        await self._async_restore()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                log_signal(self._key.lockMac),
                self._on_log_entry,
            ),
        )

    async def _async_restore(self) -> None:
        last_sensor_data = await self.async_get_last_sensor_data()
        last_state = await self.async_get_last_state()
        if last_sensor_data is None or last_state is None:
            return
        value = last_sensor_data.native_value
        self._attr_native_value = value if isinstance(value, str) else None
        attributes: TtlockBleLastUnlockAttributes = {}
        credential_type = last_state.attributes.get("credential_type")
        if isinstance(credential_type, str):
            attributes["credential_type"] = credential_type
        credential = last_state.attributes.get("credential")
        if isinstance(credential, str):
            attributes["credential"] = credential
        unlocked_at = last_state.attributes.get("unlocked_at")
        if isinstance(unlocked_at, str):
            attributes["unlocked_at"] = unlocked_at
            self._unlocked_at = dt_util.parse_datetime(unlocked_at)
        self._unlock_attributes = attributes

    @callback
    def _on_log_entry(self, record: LogEntry) -> None:
        """Adopt an unlock record as the last one, unless it is older."""
        if record.record_type not in CREDENTIAL_UNLOCK_RECORD_TYPES:
            return
        unlocked_at = record.operate_date
        if (
            unlocked_at is not None
            and self._unlocked_at is not None
            and unlocked_at < self._unlocked_at
        ):
            return
        credential = self._resolver.resolve(self._key.lockMac, record)
        attributes: TtlockBleLastUnlockAttributes = {}
        if credential.credential_type is not None:
            attributes["credential_type"] = credential.credential_type.value
        if credential.identifier is not None:
            attributes["credential"] = credential.identifier
        if unlocked_at is not None:
            attributes["unlocked_at"] = unlocked_at.isoformat()
            self._unlocked_at = unlocked_at
        self._unlock_attributes = attributes
        self._attr_native_value = credential.name or credential.identifier
        self.async_write_ha_state()
