"""End-to-end test: the diagnostics download exposes registers but no identifying data."""

import json
import socket

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mypv_elwa2_modbus import diagnostics
from custom_components.mypv_elwa2_modbus.const import CONF_UNIT_ID, DOMAIN
from tests.simulator import SERIAL_NUMBER, UNIT_ID, start_server


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def test_diagnostics_contain_registers_and_are_redacted(
    hass, enable_custom_integrations, socket_enabled
):
    port = _free_port()
    server, _ = await start_server("127.0.0.1", port)
    try:
        entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id=SERIAL_NUMBER,
            data={CONF_HOST: "127.0.0.1", CONF_PORT: port, CONF_UNIT_ID: UNIT_ID},
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)
        dump = json.dumps(result, default=str)

        # Identifying data is removed everywhere, including the raw serial registers.
        assert "127.0.0.1" not in dump
        assert SERIAL_NUMBER not in dump
        assert result["registers"]["1018"] == "**REDACTED**"

        # Raw values come with their register names from const.py.
        assert result["registers"]["1000"] == {"name": "REG_POWER", "value": 0}
        assert result["registers"]["1003"] == {"name": "REG_STATUS", "value": 3}
        assert result["registers"]["1014"] == {"name": "REG_MAX_CONTROLLED_POWER", "value": 3000}
        assert result["parsed_data"]["status_code"] == 3
        assert result["coordinator"]["is_on"] is False
    finally:
        result = server.shutdown()
        if hasattr(result, "__await__"):
            await result
