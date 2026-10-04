"""Config flow for the MyPV ELWA 2 Modbus (unofficial) integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from pymodbus.client import AsyncModbusTcpClient

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_GRID_POWER_ENTITY_ID,
    CONF_INVERT_GRID_POWER_SIGN,
    CONF_MAX_POWER,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    DEFAULT_INVERT_GRID_POWER_SIGN,
    DEFAULT_MAX_POWER,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    REG_SERIAL_NUMBER_BASE,
    REG_SERIAL_NUMBER_COUNT,
)
from .util import decode_serial_number

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
        vol.Optional(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): vol.Coerce(int),
    }
)


class CannotConnect(Exception):
    """Error to indicate we cannot connect to the device."""


async def _async_get_device_serial(host: str, port: int, unit_id: int) -> str:
    """Connect to the device and read its serial number (registers 1018-1025).

    Used both to validate the connection and as the config entry's stable
    unique ID, so the connection details can later be changed (Reconfigure)
    without affecting existing entities.
    """
    client = AsyncModbusTcpClient(host, port=port)
    try:
        await client.connect()
        if not client.connected:
            raise CannotConnect(f"Could not open a Modbus TCP connection to {host}:{port}")
        result = await client.read_holding_registers(
            REG_SERIAL_NUMBER_BASE, count=REG_SERIAL_NUMBER_COUNT, device_id=unit_id
        )
        if result.isError():
            raise CannotConnect(
                f"Modbus error reading register {REG_SERIAL_NUMBER_BASE}: {result}"
            )
        serial = decode_serial_number(result.registers)
        if not serial:
            raise CannotConnect("Device returned an empty serial number")
        return serial
    finally:
        client.close()


class MyPVElwa2ModbusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MyPV ELWA 2 Modbus (unofficial)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            unit_id = user_input[CONF_UNIT_ID]

            self._async_abort_entries_match(
                {CONF_HOST: host, CONF_PORT: port, CONF_UNIT_ID: unit_id}
            )

            try:
                serial = await _async_get_device_serial(host, port, unit_id)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during config flow validation")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"MyPV ELWA 2 ({host})", data=user_input
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry (e.g. a changed IP address)."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            unit_id = user_input[CONF_UNIT_ID]

            try:
                serial = await _async_get_device_serial(host, port, unit_id)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during reconfigure validation")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(serial)
                # Make sure the new address still points at the same
                # physical device (matched by serial number), so a typo'd
                # IP address can't silently attach this entry (and its
                # entity history) to a different AC ELWA 2.
                if serial != reconfigure_entry.unique_id:
                    return self.async_abort(reason="unique_id_mismatch")
                return self.async_update_reload_and_abort(
                    reconfigure_entry, data=user_input
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, reconfigure_entry.data
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return MyPVElwa2ModbusOptionsFlow()


class MyPVElwa2ModbusOptionsFlow(OptionsFlow):
    """Handle options for MyPV ELWA 2 Modbus (unofficial)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                ),
                vol.Optional(
                    CONF_MAX_POWER,
                    default=options.get(CONF_MAX_POWER, DEFAULT_MAX_POWER),
                ): vol.All(vol.Coerce(int), vol.Range(min=100, max=10000)),
                vol.Optional(
                    CONF_GRID_POWER_ENTITY_ID,
                    description={
                        "suggested_value": options.get(CONF_GRID_POWER_ENTITY_ID)
                    },
                ): vol.Any(
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                    None,
                ),
                vol.Optional(
                    CONF_INVERT_GRID_POWER_SIGN,
                    default=options.get(
                        CONF_INVERT_GRID_POWER_SIGN, DEFAULT_INVERT_GRID_POWER_SIGN
                    ),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
