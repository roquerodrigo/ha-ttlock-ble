"""Service handlers and registrations for the TTLock BLE integration."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, cast

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import (
    async_get as async_get_device_registry,
    format_mac,
)
from homeassistant.helpers.entity_registry import (
    async_get as async_get_entity_registry,
)
import voluptuous as vol

from ttlock_ble import TTLockError

from .const import (
    DOMAIN,
    LOGGER,
    SERVICE_CLEAR_PASSAGE_MODE,
    SERVICE_DELETE_PASSAGE_MODE,
    SERVICE_GET_AUTO_LOCK_TIME,
    SERVICE_GET_CARDS,
    SERVICE_GET_FINGERPRINTS,
    SERVICE_GET_LOCK_TIME,
    SERVICE_GET_OPERATION_LOG,
    SERVICE_GET_PASSAGE_MODE,
    SERVICE_GET_PASSCODES,
    SERVICE_SET_PASSAGE_MODE,
)
from .passage import PASSAGE_TYPE_WEEKLY

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.core import (
        HomeAssistant,
        ServiceCall,
        ServiceResponse,
    )

    from .connection import TtlockBleConnection
    from .data import TtlockBleData, TtlockBlePassageSchedule

DAY_NAME_TO_INDEX: dict[str, int] = {
    "all": 0,
    "daily": 0,
    "everyday": 0,
    "every_day": 0,
    "mon": 1,
    "monday": 1,
    "tue": 2,
    "tuesday": 2,
    "wed": 3,
    "wednesday": 3,
    "thu": 4,
    "thursday": 4,
    "fri": 5,
    "friday": 5,
    "sat": 6,
    "saturday": 6,
    "sun": 7,
    "sunday": 7,
}

DAY_INDEX_TO_NAME: dict[int, str] = {
    0: "everyday",
    1: "monday",
    2: "tuesday",
    3: "wednesday",
    4: "thursday",
    5: "friday",
    6: "saturday",
    7: "sunday",
}

SCHEMA_BASE_TARGET = {
    vol.Optional("device_id"): vol.Any(cv.string, [cv.string]),
    vol.Optional("entity_id"): vol.Any(cv.string, [cv.string]),
}

SCHEMA_GET_PASSAGE_MODE = vol.Schema(SCHEMA_BASE_TARGET)

SCHEMA_CLEAR_PASSAGE_MODE = vol.Schema(SCHEMA_BASE_TARGET)

SCHEMA_GET_OPERATION_LOG = vol.Schema(
    {
        **SCHEMA_BASE_TARGET,
        vol.Optional("max_entries", default=50): cv.positive_int,
        vol.Optional("from_sequence"): cv.positive_int,
        vol.Optional("to_sequence"): cv.positive_int,
        vol.Optional("start_date"): cv.string,
        vol.Optional("end_date"): cv.string,
    }
)

SCHEMA_SET_PASSAGE_MODE = vol.Schema(
    {
        **SCHEMA_BASE_TARGET,
        vol.Optional("start_time"): cv.string,
        vol.Optional("end_time"): cv.string,
        vol.Optional("days"): vol.Any(cv.string, int, [vol.Any(cv.string, int)]),
        vol.Optional("week_or_day"): vol.Any(cv.string, int),
        vol.Optional("all_day"): cv.boolean,
        vol.Optional("slots"): cv.ensure_list,
        vol.Optional("clear_existing", default=False): cv.boolean,
    }
)

SCHEMA_DELETE_PASSAGE_MODE = vol.Schema(
    {
        **SCHEMA_BASE_TARGET,
        vol.Required("start_time"): cv.string,
        vol.Required("end_time"): cv.string,
        vol.Optional("days"): vol.Any(cv.string, int),
        vol.Optional("week_or_day"): vol.Any(cv.string, int),
    }
)


def _parse_time_component(raw: object) -> tuple[int, int]:
    """Parse time string 'HH:MM' or time object to (hour, minute)."""
    if isinstance(raw, dt.time):
        return raw.hour, raw.minute
    if isinstance(raw, str):
        parts = raw.strip().split(":")
        if len(parts) >= 2:
            return int(parts[0]), int(parts[1])
    raise HomeAssistantError(f"Invalid time format (expected 'HH:MM'): {raw!r}")


def _parse_days(raw: object) -> list[int]:
    """Parse day input into a list of day indices (0=everyday, 1=Mon .. 7=Sun)."""
    if raw is None:
        return [0]
    if isinstance(raw, int):
        if 0 <= raw <= 7:
            return [raw]
        raise HomeAssistantError(f"Day number must be 0–7: {raw}")
    if isinstance(raw, str):
        cleaned = raw.strip().lower()
        if cleaned.isdigit():
            val = int(cleaned)
            if 0 <= val <= 7:
                return [val]
        if cleaned in DAY_NAME_TO_INDEX:
            return [DAY_NAME_TO_INDEX[cleaned]]
        raise HomeAssistantError(f"Unrecognized day name: {raw!r}")
    if isinstance(raw, (list, tuple)):
        days: list[int] = []
        for item in raw:
            days.extend(_parse_days(item))
        return list(dict.fromkeys(days))
    raise HomeAssistantError(f"Unsupported day format: {raw!r}")


def _parse_single_slot(
    item: Mapping[str, object],
) -> list[TtlockBlePassageSchedule]:
    """Parse a single schedule dictionary into one or more schedule slots."""
    if item.get("all_day"):
        start_hour, start_minute = 0, 0
        end_hour, end_minute = 23, 59
    else:
        raw_start = item.get("start_time")
        raw_end = item.get("end_time")
        if raw_start is None or raw_end is None:
            raise HomeAssistantError("Both start_time and end_time must be provided")
        start_hour, start_minute = _parse_time_component(raw_start)
        end_hour, end_minute = _parse_time_component(raw_end)

    day_input = item.get("days") if "days" in item else item.get("week_or_day")
    days = _parse_days(day_input)

    return [
        {
            "type": PASSAGE_TYPE_WEEKLY,
            "week_or_day": day,
            "month": 0,
            "start_hour": start_hour,
            "start_minute": start_minute,
            "end_hour": end_hour,
            "end_minute": end_minute,
        }
        for day in days
    ]


def _parse_schedules_from_call(
    data: Mapping[str, object],
) -> list[TtlockBlePassageSchedule]:
    """Parse service call parameters into a list of TtlockBlePassageSchedule slots."""
    raw_slots = data.get("slots")
    if raw_slots and isinstance(raw_slots, list):
        schedules: list[TtlockBlePassageSchedule] = []
        for slot in raw_slots:
            if isinstance(slot, dict):
                schedules.extend(_parse_single_slot(cast("Mapping[str, object]", slot)))
        return schedules

    return _parse_single_slot(data)


def _async_resolve_connections(
    hass: HomeAssistant,
    call: ServiceCall,
) -> list[TtlockBleConnection]:
    """Resolve target device_id or entity_id to TtlockBleConnection instances."""
    device_registry = async_get_device_registry(hass)
    entity_registry = async_get_entity_registry(hass)

    connections_by_mac: dict[str, TtlockBleConnection] = {}
    for entry in hass.config_entries.async_entries(DOMAIN):
        entry_data: TtlockBleData | None = getattr(entry, "runtime_data", None)
        if entry_data is not None:
            connections_by_mac.update(entry_data.connections)

    if not connections_by_mac:
        raise HomeAssistantError("No TTLock BLE devices loaded")

    target_macs: set[str] = set()

    device_ids: list[str] = []
    if "device_id" in call.data:
        raw_dev = call.data["device_id"]
        device_ids.extend([raw_dev] if isinstance(raw_dev, str) else list(raw_dev))

    if "entity_id" in call.data:
        raw_ent = call.data["entity_id"]
        entity_ids = [raw_ent] if isinstance(raw_ent, str) else list(raw_ent)
        for ent_id in entity_ids:
            ent = entity_registry.async_get(ent_id)
            if ent and ent.device_id:
                device_ids.append(ent.device_id)

    for dev_id in device_ids:
        dev = device_registry.async_get(dev_id)
        if dev:
            for domain, identifier in dev.identifiers:
                if domain == DOMAIN:
                    target_macs.add(identifier)

    if target_macs:
        resolved: list[TtlockBleConnection] = []
        for mac, conn in connections_by_mac.items():
            if format_mac(mac) in target_macs or mac.lower() in target_macs:
                resolved.append(conn)
        if not resolved:
            raise HomeAssistantError(
                f"No matching TTLock BLE lock found for specified target(s): {target_macs}"
            )
        return resolved

    if len(connections_by_mac) == 1:
        return list(connections_by_mac.values())

    raise HomeAssistantError(
        "Multiple TTLock locks are present; please specify a target device_id or entity_id"
    )


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register TTLock BLE actions / services with Home Assistant."""
    if hass.services.has_service(DOMAIN, SERVICE_GET_PASSAGE_MODE):
        return

    async def async_handle_get_passage_mode(call: ServiceCall) -> ServiceResponse:
        """Handle ttlock_ble.get_passage_mode."""
        connections = _async_resolve_connections(hass, call)
        results: list[dict[str, object]] = []
        for conn in connections:
            try:
                schedules = await conn.async_get_passage_mode()
                for slot in schedules:
                    results.append({
                        "lock_mac": conn.key.lockMac,
                        "week_or_day": slot["week_or_day"],
                        "day_name": DAY_INDEX_TO_NAME.get(
                            slot["week_or_day"],
                            "everyday",
                        ),
                        "start_time": (
                            f"{slot['start_hour']:02d}:{slot['start_minute']:02d}"
                        ),
                        "end_time": (
                            f"{slot['end_hour']:02d}:{slot['end_minute']:02d}"
                        ),
                        "type": slot["type"],
                        "month": slot["month"],
                    })
            except TTLockError as exc:
                raise HomeAssistantError(
                    f"Failed to query passage mode for {conn.key.lockMac}: {exc}"
                ) from exc
        return {"schedules": results}

    async def async_handle_set_passage_mode(call: ServiceCall) -> None:
        """Handle ttlock_ble.set_passage_mode."""
        connections = _async_resolve_connections(hass, call)
        schedules = _parse_schedules_from_call(call.data)
        clear_existing = bool(call.data.get("clear_existing", False))
        for conn in connections:
            try:
                await conn.async_set_passage_mode(
                    schedules,
                    clear_existing=clear_existing,
                )
            except TTLockError as exc:
                raise HomeAssistantError(
                    f"Failed to set passage mode for {conn.key.lockMac}: {exc}"
                ) from exc

    async def async_handle_delete_passage_mode(call: ServiceCall) -> None:
        """Handle ttlock_ble.delete_passage_mode."""
        connections = _async_resolve_connections(hass, call)
        slots = _parse_schedules_from_call(call.data)
        for conn in connections:
            for slot in slots:
                try:
                    await conn.async_delete_passage_mode(slot)
                except TTLockError as exc:
                    raise HomeAssistantError(
                        f"Failed to delete passage mode slot for {conn.key.lockMac}: {exc}"
                    ) from exc

    async def async_handle_clear_passage_mode(call: ServiceCall) -> None:
        """Handle ttlock_ble.clear_passage_mode."""
        connections = _async_resolve_connections(hass, call)
        for conn in connections:
            try:
                await conn.async_clear_passage_mode()
            except TTLockError as exc:
                raise HomeAssistantError(
                    f"Failed to clear passage mode for {conn.key.lockMac}: {exc}"
                ) from exc

    async def async_handle_get_auto_lock_time(call: ServiceCall) -> ServiceResponse:
        """Handle ttlock_ble.get_auto_lock_time."""
        connections = _async_resolve_connections(hass, call)
        results: list[dict[str, object]] = []
        for conn in connections:
            try:
                info = await conn.async_get_auto_lock_info()
                results.append({"lock_mac": conn.key.lockMac, **info})
            except Exception as exc:
                raise HomeAssistantError(
                    f"Failed to get auto-lock time for {conn.key.lockMac}: {exc}"
                ) from exc
        return {"auto_lock": results}

    async def async_handle_get_lock_time(call: ServiceCall) -> ServiceResponse:
        """Handle ttlock_ble.get_lock_time."""
        connections = _async_resolve_connections(hass, call)
        results: list[dict[str, object]] = []
        for conn in connections:
            try:
                clock_info = await conn.async_get_lock_clock()
                results.append({"lock_mac": conn.key.lockMac, **clock_info})
            except Exception as exc:
                raise HomeAssistantError(
                    f"Failed to get clock time for {conn.key.lockMac}: {exc}"
                ) from exc
        return {"lock_times": results}

    async def async_handle_get_operation_log(call: ServiceCall) -> ServiceResponse:
        """Handle ttlock_ble.get_operation_log."""
        connections = _async_resolve_connections(hass, call)
        max_entries = int(call.data.get("max_entries", 50))
        from_sequence = call.data.get("from_sequence")
        from_seq_int = int(from_sequence) if from_sequence is not None else None
        to_sequence = call.data.get("to_sequence")
        to_seq_int = int(to_sequence) if to_sequence is not None else None
        start_date = call.data.get("start_date")
        end_date = call.data.get("end_date")
        results: list[dict[str, object]] = []
        for conn in connections:
            try:
                records = await conn.async_fetch_operation_log(
                    max_entries=max_entries,
                    from_sequence=from_seq_int,
                    to_sequence=to_seq_int,
                    start_date=start_date,
                    end_date=end_date,
                )
                for rec in records:
                    results.append({"lock_mac": conn.key.lockMac, **rec})
            except Exception as exc:
                raise HomeAssistantError(
                    f"Failed to get operation log for {conn.key.lockMac}: {exc}"
                ) from exc
        return {"records": results}

    async def async_handle_get_passcodes(call: ServiceCall) -> ServiceResponse:
        """Handle ttlock_ble.get_passcodes."""
        connections = _async_resolve_connections(hass, call)
        results: list[dict[str, object]] = []
        for conn in connections:
            try:
                codes = await conn.async_get_passcodes()
                for code in codes:
                    results.append({"lock_mac": conn.key.lockMac, **code})
            except Exception as exc:
                raise HomeAssistantError(
                    f"Failed to get passcodes for {conn.key.lockMac}: {exc}"
                ) from exc
        return {"passcodes": results}

    async def async_handle_get_cards(call: ServiceCall) -> ServiceResponse:
        """Handle ttlock_ble.get_cards."""
        connections = _async_resolve_connections(hass, call)
        results: list[dict[str, object]] = []
        for conn in connections:
            try:
                cards = await conn.async_get_cards()
                for card in cards:
                    results.append({"lock_mac": conn.key.lockMac, **card})
            except Exception as exc:
                raise HomeAssistantError(
                    f"Failed to get cards for {conn.key.lockMac}: {exc}"
                ) from exc
        return {"cards": results}

    async def async_handle_get_fingerprints(call: ServiceCall) -> ServiceResponse:
        """Handle ttlock_ble.get_fingerprints."""
        connections = _async_resolve_connections(hass, call)
        results: list[dict[str, object]] = []
        for conn in connections:
            try:
                fps = await conn.async_get_fingerprints()
                for fp in fps:
                    results.append({"lock_mac": conn.key.lockMac, **fp})
            except Exception as exc:
                raise HomeAssistantError(
                    f"Failed to get fingerprints for {conn.key.lockMac}: {exc}"
                ) from exc
        return {"fingerprints": results}

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_PASSAGE_MODE,
        async_handle_get_passage_mode,
        schema=SCHEMA_GET_PASSAGE_MODE,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PASSAGE_MODE,
        async_handle_set_passage_mode,
        schema=SCHEMA_SET_PASSAGE_MODE,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_PASSAGE_MODE,
        async_handle_delete_passage_mode,
        schema=SCHEMA_DELETE_PASSAGE_MODE,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_PASSAGE_MODE,
        async_handle_clear_passage_mode,
        schema=SCHEMA_CLEAR_PASSAGE_MODE,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_AUTO_LOCK_TIME,
        async_handle_get_auto_lock_time,
        schema=SCHEMA_GET_PASSAGE_MODE,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_LOCK_TIME,
        async_handle_get_lock_time,
        schema=SCHEMA_GET_PASSAGE_MODE,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_OPERATION_LOG,
        async_handle_get_operation_log,
        schema=SCHEMA_GET_OPERATION_LOG,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_PASSCODES,
        async_handle_get_passcodes,
        schema=SCHEMA_GET_PASSAGE_MODE,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_CARDS,
        async_handle_get_cards,
        schema=SCHEMA_GET_PASSAGE_MODE,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_FINGERPRINTS,
        async_handle_get_fingerprints,
        schema=SCHEMA_GET_PASSAGE_MODE,
        supports_response=SupportsResponse.OPTIONAL,
    )
    LOGGER.debug("Registered TTLock BLE services")


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unregister TTLock BLE services when integration is completely unloaded."""
    if any(
        entry.state == ConfigEntryState.LOADED
        for entry in hass.config_entries.async_entries(DOMAIN)
    ):
        return

    hass.services.async_remove(DOMAIN, SERVICE_GET_PASSAGE_MODE)
    hass.services.async_remove(DOMAIN, SERVICE_SET_PASSAGE_MODE)
    hass.services.async_remove(DOMAIN, SERVICE_DELETE_PASSAGE_MODE)
    hass.services.async_remove(DOMAIN, SERVICE_CLEAR_PASSAGE_MODE)
    hass.services.async_remove(DOMAIN, SERVICE_GET_AUTO_LOCK_TIME)
    hass.services.async_remove(DOMAIN, SERVICE_GET_LOCK_TIME)
    hass.services.async_remove(DOMAIN, SERVICE_GET_OPERATION_LOG)
    hass.services.async_remove(DOMAIN, SERVICE_GET_PASSCODES)
    hass.services.async_remove(DOMAIN, SERVICE_GET_CARDS)
    hass.services.async_remove(DOMAIN, SERVICE_GET_FINGERPRINTS)
    LOGGER.debug("Unregistered TTLock BLE services")
