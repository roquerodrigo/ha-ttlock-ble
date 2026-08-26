"""Options flow for ttlock_ble."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.helpers import selector

from .const import CONF_PERMANENT_CONNECTION

if TYPE_CHECKING:
    from .data import TtlockBleOptionsData


class TtlockBleOptionsFlow(OptionsFlow):
    """Options flow for TTLock BLE."""

    async def async_step_init(
        self,
        user_input: TtlockBleOptionsData | None = None,
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=dict(user_input))

        current_permanent_connection: bool = self.config_entry.options.get(
            CONF_PERMANENT_CONNECTION,
            False,
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_PERMANENT_CONNECTION,
                        default=current_permanent_connection,
                    ): selector.BooleanSelector(),
                },
            ),
        )
