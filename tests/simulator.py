"""Minimal AC ELWA 2 Modbus TCP simulator for tests and local development.

Run standalone (e.g. as a docker compose service):
    python -m tests.simulator

Environment:
    MODBUS_PORT  port to listen on, default 502
"""

from __future__ import annotations

import asyncio
import os

from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext
from pymodbus.server import ModbusTcpServer

# Fake serial number in the format my-PV uses (product prefix + digits).
SERIAL_NUMBER = "1601500000000001"
UNIT_ID = 1
REGISTER_COUNT = 1100

REG_SERIAL_BASE = 1018
REG_SERIAL_COUNT = 8


def _initial_registers() -> list[int]:
    values = [0] * REGISTER_COUNT
    values[1001] = 265  # temperature 1: 26.5 °C
    values[1002] = 605  # target temperature: 60.5 °C
    values[1003] = 3  # status: standby
    values[1014] = 3000  # max controlled power (W)
    values[1016] = 4  # controller firmware main version
    values[1017] = 1  # power stage firmware ("ep001")
    values[1028] = 18  # controller firmware sub version
    values[1061] = 230  # mains voltage (V)
    values[1065] = 1  # operation mode: mode 1
    values[1071] = 3000  # max available power (W)
    values[1077] = 0  # operation state: standby
    values[1081] = 1  # device state: enabled
    values[1086] = 5  # co-controller firmware ("ec005")
    chars = SERIAL_NUMBER.ljust(REG_SERIAL_COUNT * 2, "\x00")
    for i in range(REG_SERIAL_COUNT):
        values[REG_SERIAL_BASE + i] = (ord(chars[2 * i]) << 8) | ord(chars[2 * i + 1])
    return values


def build_holding_registers() -> ModbusSequentialDataBlock:
    return ModbusSequentialDataBlock(1, _initial_registers())


def build_server(holding_registers: ModbusSequentialDataBlock) -> ModbusServerContext:
    device = ModbusDeviceContext(hr=holding_registers)
    return ModbusServerContext(devices={UNIT_ID: device}, single=False)


async def start_server(
    host: str, port: int, holding_registers: ModbusSequentialDataBlock | None = None
) -> tuple[ModbusTcpServer, ModbusSequentialDataBlock]:
    """Start the simulator in the running event loop.

    Returns the server and the holding register block, which tests can write
    to. Pass an existing block to restart the server with the same state.
    """
    holding_registers = holding_registers or build_holding_registers()
    server = ModbusTcpServer(build_server(holding_registers), address=(host, port))
    await server.serve_forever(background=True)
    await asyncio.sleep(0.2)  # let the background listener start accepting connections
    return server, holding_registers


async def _main() -> None:
    port = int(os.environ.get("MODBUS_PORT", "502"))
    await start_server("0.0.0.0", port)
    print(f"AC ELWA 2 simulator listening on port {port}", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(_main())
