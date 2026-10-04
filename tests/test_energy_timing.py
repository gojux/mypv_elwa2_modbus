"""End-to-end test: energy uses the measured time between polls, not the scan interval."""

import socket

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import entity_registry as er
from pymodbus.client import AsyncModbusTcpClient
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mypv_elwa2_modbus.const import CONF_UNIT_ID, DOMAIN
from tests.simulator import SERIAL_NUMBER, UNIT_ID, start_server

FULL_POWER_W = 3000


def _kwh(seconds: float) -> float:
    return round(FULL_POWER_W * seconds / 3600 / 1000, 4)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _set_power(port: int, watts: int) -> None:
    client = AsyncModbusTcpClient("127.0.0.1", port=port)
    await client.connect()
    await client.write_registers(1000, [watts], device_id=UNIT_ID)
    client.close()


def _energy_state(hass) -> float:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{SERIAL_NUMBER}_energy"
    )
    return float(hass.states.get(entity_id).state)


async def test_manual_listener_update_adds_no_energy(
    hass, enable_custom_integrations, socket_enabled, fake_clock
):
    port = _free_port()
    server, _ = await start_server("127.0.0.1", port)
    try:
        await _set_power(port, FULL_POWER_W)
        entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id=SERIAL_NUMBER,
            data={CONF_HOST: "127.0.0.1", CONF_PORT: port, CONF_UNIT_ID: UNIT_ID},
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        fake_clock.advance(5)
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert _energy_state(hass) == _kwh(5)

        # Auto-control style updates reuse the same snapshot: no new energy.
        for _ in range(10):
            entry.runtime_data.async_update_listeners()
        await hass.async_block_till_done()
        assert _energy_state(hass) == _kwh(5)
    finally:
        result = server.shutdown()
        if hasattr(result, "__await__"):
            await result


async def test_explicit_refresh_counts_only_measured_time(
    hass, enable_custom_integrations, socket_enabled, fake_clock
):
    port = _free_port()
    server, _ = await start_server("127.0.0.1", port)
    try:
        await _set_power(port, FULL_POWER_W)
        entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id=SERIAL_NUMBER,
            data={CONF_HOST: "127.0.0.1", CONF_PORT: port, CONF_UNIT_ID: UNIT_ID},
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        fake_clock.advance(5)
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()

        # An action-triggered refresh 2 s later must count 2 s, not a full
        # scan interval of 5 s.
        fake_clock.advance(2)
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert _energy_state(hass) == _kwh(7)
    finally:
        result = server.shutdown()
        if hasattr(result, "__await__"):
            await result
