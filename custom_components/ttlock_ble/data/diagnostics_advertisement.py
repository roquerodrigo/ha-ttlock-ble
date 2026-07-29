"""Last advertisement seen for one lock, as captured in the diagnostics dump."""

from __future__ import annotations

from typing import TypedDict


class TtlockBleDiagnosticsAdvertisement(TypedDict):
    """
    Last advertisement seen for one lock, as captured in the diagnostics dump.

    `manufacturer_data` carries the raw bytes per company id, hex-encoded.
    Keeping them in the dump is what makes a "state never updates" report
    diagnosable: `decoded` is `None` whenever the payload does not match
    the layout this integration knows, and the raw bytes are then the
    only way to tell which layout the firmware actually uses.
    """

    source: str
    rssi: int
    manufacturer_data: dict[str, str]
    decoded: dict[str, str | int | bool] | None
