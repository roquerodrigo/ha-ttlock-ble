"""Entry section of the diagnostics dump."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from collections.abc import Mapping


class TtlockBleDiagnosticsEntry(TypedDict):
    """Entry section of the diagnostics dump."""

    title: str
    version: int
    domain: str
    data: Mapping[str, str | int]
    options: Mapping[str, str | int]
