"""End-to-end tests: water heater on/off and automatic grid-surplus control."""

import asyncio
import socket

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import entity_registry as er
from pymodbus.client import AsyncModbusTcpClient
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mypv_elwa2_modbus.const import (
    CONF_GRID_POWER_ENTITY_ID,
    CONF_UNIT_ID,
    DOMAIN,
)
from tests.simulator import SERIAL_NUMBER, UNIT_ID, start_server

GRID_ENTITY_ID = "sensor.grid_power"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _entity_id(hass, domain: str, suffix: str) -> str:
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{SERIAL_NUMBER}_{suffix}")


async def _read_power(port: int) -> int:
    client = AsyncModbusTcpClient("127.0.0.1", port=port)
    await client.connect()
    result = await client.read_holding_registers(1000, count=1, device_id=UNIT_ID)
    client.close()
    return result.registers[0]


async def _setup(hass, port: int):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERIAL_NUMBER,
        data={CONF_HOST: "127.0.0.1", CONF_PORT: port, CONF_UNIT_ID: UNIT_ID},
        options={CONF_GRID_POWER_ENTITY_ID: GRID_ENTITY_ID},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _shutdown(server) -> None:
    result = server.shutdown()
    if hasattr(result, "__await__"):
        await result


async def _call(hass, domain: str, service: str, entity_id: str, **data) -> None:
    await hass.services.async_call(
        domain, service, {"entity_id": entity_id, **data}, blocking=True
    )
    await hass.async_block_till_done()


async def _setup_auto_control(hass, port: int, grid_watts: str = "800"):
    """Set up the integration with automatic control enabled, but the heater off.

    Smoothing is disabled so every grid value enters the calculation as is.
    """
    entry = await _setup(hass, port)
    hass.states.async_set(GRID_ENTITY_ID, grid_watts)
    await hass.async_block_till_done()
    smoothing = _entity_id(hass, "number", "auto_smoothing")
    auto = _entity_id(hass, "switch", "auto_control")
    assert smoothing is not None
    assert auto is not None
    await _call(hass, "number", "set_value", smoothing, value=0)
    await _call(hass, "switch", "turn_on", auto)
    return entry


async def test_turn_on_restores_manual_power_when_auto_control_is_off(
    hass, enable_custom_integrations, socket_enabled
):
    port = _free_port()
    server, _ = await start_server("127.0.0.1", port)
    try:
        entry = await _setup(hass, port)
        power = _entity_id(hass, "number", "power_setpoint")
        heater = _entity_id(hass, "water_heater", "water_heater")

        await _call(hass, "number", "set_value", power, value=2500)
        assert await _read_power(port) == 2500

        await _call(hass, "water_heater", "turn_off", heater)
        assert await _read_power(port) == 0

        await _call(hass, "water_heater", "turn_on", heater)
        assert await _read_power(port) == 2500
        assert entry.runtime_data.last_power_setpoint == 2500
    finally:
        await _shutdown(server)


async def test_turn_on_under_auto_control_starts_from_grid_surplus(
    hass, enable_custom_integrations, socket_enabled
):
    port = _free_port()
    server, _ = await start_server("127.0.0.1", port)
    try:
        entry = await _setup(hass, port)
        power = _entity_id(hass, "number", "power_setpoint")
        heater = _entity_id(hass, "water_heater", "water_heater")
        auto = _entity_id(hass, "switch", "auto_control")

        # Establish a manual value that must NOT be restored under auto control.
        await _call(hass, "number", "set_value", power, value=2500)
        await _call(hass, "water_heater", "turn_off", heater)
        assert await _read_power(port) == 0

        hass.states.async_set(GRID_ENTITY_ID, "800")
        await hass.async_block_till_done()
        await _call(hass, "switch", "turn_on", auto)

        await _call(hass, "water_heater", "turn_on", heater)
        # Device power is 0 W while off, so the result is 0 + 800 W surplus
        # - 100 W default reserve = 700 W, not the stored 2500 W.
        assert await _read_power(port) == 700
        assert entry.runtime_data.last_power_setpoint == 2500
    finally:
        await _shutdown(server)


async def test_enabling_auto_control_while_on_applies_immediately(
    hass, enable_custom_integrations, socket_enabled
):
    port = _free_port()
    server, _ = await start_server("127.0.0.1", port)
    try:
        await _setup(hass, port)
        power = _entity_id(hass, "number", "power_setpoint")
        auto = _entity_id(hass, "switch", "auto_control")

        await _call(hass, "number", "set_value", power, value=2500)
        assert await _read_power(port) == 2500

        hass.states.async_set(GRID_ENTITY_ID, "300")
        await hass.async_block_till_done()
        await _call(hass, "switch", "turn_on", auto)

        # Without a new grid state change: 2500 W + 300 W surplus - 100 W reserve.
        assert await _read_power(port) == 2700
    finally:
        await _shutdown(server)


async def test_power_number_is_ignored_while_auto_control_is_on(
    hass, enable_custom_integrations, socket_enabled
):
    port = _free_port()
    server, _ = await start_server("127.0.0.1", port)
    try:
        entry = await _setup_auto_control(hass, port)
        power = _entity_id(hass, "number", "power_setpoint")

        await _call(hass, "number", "set_value", power, value=1234)

        assert await _read_power(port) == 0
        assert entry.runtime_data.is_on is False
    finally:
        await _shutdown(server)


async def test_auto_control_pauses_while_water_heater_is_off(
    hass, enable_custom_integrations, socket_enabled
):
    port = _free_port()
    server, _ = await start_server("127.0.0.1", port)
    try:
        await _setup_auto_control(hass, port)
        heater = _entity_id(hass, "water_heater", "water_heater")

        # Enabling it while off must not write anything.
        assert await _read_power(port) == 0

        await _call(hass, "water_heater", "turn_on", heater)
        assert await _read_power(port) == 700

        await _call(hass, "water_heater", "turn_off", heater)
        assert await _read_power(port) == 0

        # A grid change while off must not restart the device.
        hass.states.async_set(GRID_ENTITY_ID, "500")
        await hass.async_block_till_done()
        assert await _read_power(port) == 0
    finally:
        await _shutdown(server)


async def test_failed_write_rolls_back_rate_limit(
    hass, enable_custom_integrations, socket_enabled
):
    port = _free_port()
    server, registers = await start_server("127.0.0.1", port)
    try:
        entry = await _setup_auto_control(hass, port)
        heater = _entity_id(hass, "water_heater", "water_heater")
        await _call(hass, "water_heater", "turn_on", heater)
        assert await _read_power(port) == 700
        last_successful_write = entry.runtime_data._auto_control_last_write

        # Wait past the one-second rate limit, so the next event is due.
        await asyncio.sleep(1.1)

        # This write fails because the device is offline. The Modbus retries
        # take a few seconds, so the failed attempt must not stay on record as
        # a write. Otherwise the retry below would be held back by the rate limit.
        result = server.shutdown()
        if hasattr(result, "__await__"):
            await result
        hass.states.async_set(GRID_ENTITY_ID, "900")
        await hass.async_block_till_done()
        assert entry.runtime_data._auto_control_last_write == last_successful_write

        # The device is back: 700 W + 1000 W surplus - 100 W reserve = 1600 W.
        server, _ = await start_server("127.0.0.1", port, holding_registers=registers)
        hass.states.async_set(GRID_ENTITY_ID, "1000")
        await hass.async_block_till_done()
        assert await _read_power(port) == 1600
        assert entry.runtime_data.power_setpoint == 1600
    finally:
        await _shutdown(server)


async def test_queued_grid_event_uses_updated_base(
    hass, enable_custom_integrations, socket_enabled
):
    port = _free_port()
    server, _ = await start_server("127.0.0.1", port)
    try:
        entry = await _setup_auto_control(hass, port)
        heater = _entity_id(hass, "water_heater", "water_heater")
        await _call(hass, "water_heater", "turn_on", heater)
        assert await _read_power(port) == 700

        # Hold the Modbus lock, so the next automatic write has to wait for it.
        await asyncio.sleep(1.1)
        await entry.runtime_data._lock.acquire()
        try:
            # First event: computes 700 + 1000 - 100 = 1600 and waits for the lock.
            hass.states.async_set(GRID_ENTITY_ID, "1000")
            await asyncio.sleep(0.05)

            # Second event arrives after the rate limit has passed, while the
            # first one is still waiting. It must build on the first result
            # (1600 W), not on the stale 700 W: 1600 + 500 - 100 = 2000 W.
            await asyncio.sleep(1.1)
            hass.states.async_set(GRID_ENTITY_ID, "500")
            await asyncio.sleep(0.05)
        finally:
            entry.runtime_data._lock.release()
        await hass.async_block_till_done()

        assert await _read_power(port) == 2000
    finally:
        await _shutdown(server)
