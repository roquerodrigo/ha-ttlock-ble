"""Device-registry identifiers of the fingerprint devices under each lock."""

from __future__ import annotations

from homeassistant.helpers.device_registry import format_mac

from .const import DOMAIN
from .data import TtlockBleEnrolledFingerprint


def lock_identifier(mac: str) -> tuple[str, str]:
    """Return the identifier of the lock's own device."""
    return (DOMAIN, format_mac(mac))


def fingerprints_hub_identifier(mac: str) -> tuple[str, str]:
    """Return the identifier of the device grouping a lock's fingerprints."""
    return (DOMAIN, f"{format_mac(mac)}_fingerprints")


def fingerprint_identifier(
    mac: str, fingerprint: TtlockBleEnrolledFingerprint
) -> tuple[str, str]:
    """Return the identifier of one fingerprint's device."""
    return (DOMAIN, f"{_fingerprint_prefix(mac)}{fingerprint.token}")


def enrolled_fingerprint_of(
    identifiers: set[tuple[str, str]], mac: str
) -> TtlockBleEnrolledFingerprint | None:
    """Return the fingerprint a registry device's identifiers stand for, if any."""
    prefix = _fingerprint_prefix(mac)
    for domain, identifier in identifiers:
        if domain == DOMAIN and identifier.startswith(prefix):
            return TtlockBleEnrolledFingerprint.from_token(
                identifier.removeprefix(prefix)
            )
    return None


def lock_mac_of(identifier: str) -> str:
    """Return the formatted MAC of the lock an identifier belongs to."""
    return identifier.split("_", 1)[0]


def _fingerprint_prefix(mac: str) -> str:
    return f"{format_mac(mac)}_fingerprint_"
