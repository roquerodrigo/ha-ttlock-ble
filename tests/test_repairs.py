from __future__ import annotations

from homeassistant.components.repairs import ConfirmRepairFlow
from homeassistant.helpers import issue_registry as ir

from custom_components.integration_blueprint.const import DOMAIN
from custom_components.integration_blueprint.repairs import (
    ISSUE_DEPRECATED_API,
    async_create_fix_flow,
    async_raise_deprecated_api_issue,
)


async def test_create_fix_flow_returns_confirm_flow(hass):
    flow = await async_create_fix_flow(hass, ISSUE_DEPRECATED_API, None)
    assert isinstance(flow, ConfirmRepairFlow)


async def test_raise_deprecated_api_issue_registers_issue(hass):
    async_raise_deprecated_api_issue(hass)
    registry = ir.async_get(hass)
    issue = registry.async_get_issue(DOMAIN, ISSUE_DEPRECATED_API)
    assert issue is not None
    assert issue.is_fixable is True
    assert issue.severity == ir.IssueSeverity.WARNING
    assert issue.translation_key == ISSUE_DEPRECATED_API


async def test_raise_deprecated_api_issue_idempotent(hass):
    async_raise_deprecated_api_issue(hass)
    async_raise_deprecated_api_issue(hass)
    registry = ir.async_get(hass)
    matching = [
        i
        for i in registry.issues.values()
        if i.domain == DOMAIN and i.issue_id == ISSUE_DEPRECATED_API
    ]
    assert len(matching) == 1
