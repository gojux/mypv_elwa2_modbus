"""End-to-end test: set up the integration via the config flow against the simulator."""

import socket

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.mypv_elwa2_modbus.const import CONF_UNIT_ID, DOMAIN
from tests.simulator import SERIAL_NUMBER, UNIT_ID, start_server


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def test_config_flow_sets_up_device_and_entities(
    hass, enable_custom_integrations, socket_enabled
):
    port = _free_port()
    server, _ = await start_server("127.0.0.1", port)
    try:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "127.0.0.1", CONF_PORT: port, CONF_UNIT_ID: UNIT_ID},
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()

        entry = result["result"]
        assert entry.unique_id == SERIAL_NUMBER
        assert entry.state is config_entries.ConfigEntryState.LOADED

        device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, SERIAL_NUMBER)})
        assert device is not None
        assert device.serial_number == SERIAL_NUMBER

        entity_id = er.async_get(hass).async_get_entity_id(
            "sensor", DOMAIN, f"{SERIAL_NUMBER}_power"
        )
        assert entity_id is not None
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == "0"
    finally:
        result = server.shutdown()
        if hasattr(result, "__await__"):
            await result
