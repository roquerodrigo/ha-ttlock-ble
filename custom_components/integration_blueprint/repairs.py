"""
Repairs platform for integration_blueprint.

Wires this integration into Home Assistant's Issue / Repair Registry. Use
``async_raise_deprecated_api_issue`` (or your own helper) from anywhere in the
integration to surface a recoverable problem to the user; the UI exposes the
"Fix" button which routes back here through ``async_create_fix_flow``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

ISSUE_DEPRECATED_API: str = "deprecated_api"

# HA's contract for the data argument passed to async_create_fix_flow.
type RepairsFixFlowData = dict[str, str | int | float | None]


async def async_create_fix_flow(
    hass: HomeAssistant,  # noqa: ARG001
    issue_id: str,  # noqa: ARG001
    data: RepairsFixFlowData | None,  # noqa: ARG001
) -> RepairsFlow:
    """
    Return the fix flow for a given issue.

    Branch on ``issue_id`` here when you have multiple kinds of issues.
    """
    return ConfirmRepairFlow()


def async_raise_deprecated_api_issue(hass: HomeAssistant) -> None:
    """
    Sample helper: raise the deprecated-API issue.

    Call this from the coordinator / setup when you detect the recoverable
    condition the issue describes.
    """
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_DEPRECATED_API,
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_DEPRECATED_API,
    )
