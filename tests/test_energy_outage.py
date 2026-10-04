"""End-to-end test: energy must not be extrapolated over a device outage."""

import socket

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import entity_registry as er
from pymodbus.client import AsyncModbusTcpClient
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mypv_elwa2_modbus.const import CONF_UNIT_ID, DOMAIN
from tests.simulator import SERIAL_NUMBER, UNIT_ID, start_server

FULL_POWER_W = 3000
UPDATE_INTERVAL_S = 5
KWH_PER_STEP = FULL_POWER_W * UPDATE_INTERVAL_S / 3600 / 1000


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _set_power(port: int, watts: int) -> None:
    client = AsyncModbusTcpClient("127.0.0.1", port=port)
    await client.connect()
    await client.write_registers(1000, [watts], device_id=UNIT_ID)
    client.close()


async def _refresh(hass, entry, clock) -> None:
    # Each refresh stands for one scan interval that has passed on the clock.
    clock.advance(UPDATE_INTERVAL_S)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


def _energy_state_raw(hass) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{SERIAL_NUMBER}_energy"
    )
    return hass.states.get(entity_id).state


def _energy_state(hass) -> float:
    return float(_energy_state_raw(hass))


async def test_energy_is_not_extrapolated_over_outage(
    hass, enable_custom_integrations, socket_enabled, fake_clock
):
    port = _free_port()
    server, registers = await start_server("127.0.0.1", port)
    await _set_power(port, FULL_POWER_W)

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERIAL_NUMBER,
        data={CONF_HOST: "127.0.0.1", CONF_PORT: port, CONF_UNIT_ID: UNIT_ID},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # The setup poll sets the reference time, so three refreshes add three
    # measured intervals.
    try:
        for _ in range(3):
            await _refresh(hass, entry, fake_clock)
        assert _energy_state(hass) == round(3 * KWH_PER_STEP, 4)

        # Device offline: failing updates must not add energy.
        result = server.shutdown()
        if hasattr(result, "__await__"):
            await result
        for _ in range(3):
            await _refresh(hass, entry, fake_clock)
        assert _energy_state_raw(hass) == "unavailable"

        # Device back: the first successful update after an outage has no
        # interval (no previous poll to measure from), the following one adds
        # exactly one interval.
        server, _ = await start_server("127.0.0.1", port, holding_registers=registers)
        await _set_power(port, FULL_POWER_W)
        await _refresh(hass, entry, fake_clock)
        assert entry.runtime_data.last_update_success, "update after restart failed"
        assert _energy_state(hass) == round(3 * KWH_PER_STEP, 4)

        await _refresh(hass, entry, fake_clock)
        assert entry.runtime_data.last_update_success, "second update after restart failed"
        assert _energy_state(hass) == round(4 * KWH_PER_STEP, 4)
    finally:
        result = server.shutdown()
        if hasattr(result, "__await__"):
            await result
