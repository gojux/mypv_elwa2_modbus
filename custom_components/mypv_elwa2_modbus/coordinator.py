"""DataUpdateCoordinator for the MyPV ELWA 2 Modbus (unofficial) integration."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    HEATING_STATUS_CODES,
    REG_BASE,
    REG_CO_CONTROLLER_FW_VERSION,
    REG_CONTROLLER_FW_MAIN_VERSION,
    REG_CONTROLLER_FW_SUB_VERSION,
    REG_COUNT,
    REG_DEVICE_STATE,
    REG_MAX_AVAILABLE_POWER,
    REG_MAX_CONTROLLED_POWER,
    REG_OPERATION_MODE,
    REG_OPERATION_STATE,
    REG_POWER,
    REG_POWERSTAGE_FW_VERSION,
    REG_RELAY_STATE,
    REG_SERIAL_NUMBER_BASE,
    REG_SERIAL_NUMBER_COUNT,
    REG_STATUS,
    REG_TARGET_TEMPERATURE,
    REG_TEMP_T1,
    REG_TEMP_T2,
    REG_VOLTAGE,
    STORAGE_KEY_LAST_POWER_SETPOINT,
    STORAGE_VERSION,
)
from .util import decode_serial_number

_LOGGER = logging.getLogger(__name__)


@dataclass
class MyPVElwa2Data:
    """A single snapshot of AC ELWA 2 Modbus data."""

    power: int
    temperature: float
    temperature_2: float
    target_temperature: float
    status_code: int
    operation_state: int
    operation_mode: int
    aux_relay_active: bool
    selv_relay_active: bool
    voltage: int
    max_controlled_power: int
    max_available_power: int
    device_enabled: bool
    heating_active: bool
    serial_number: str
    firmware_version: str
    powerstage_firmware_version: str
    co_controller_firmware_version: str


class MyPVElwa2ModbusCoordinator(DataUpdateCoordinator[MyPVElwa2Data]):
    """Poll an AC ELWA 2 over Modbus TCP and keep manual power set-points alive."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        host: str,
        port: int,
        unit_id: int,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=entry.title,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.entry = entry
        self.host = host
        self.port = port
        self.unit_id = unit_id
        # The device's serial number (set as the config entry's unique ID
        # during the config/reconfigure flow) is used as the stable device
        # identifier, independent of host/port, so that changing the IP
        # address later (Reconfigure) does not create new entities.
        self.unique_id = entry.unique_id or f"{host}_{port}_{unit_id}"
        self.device_name = entry.title

        self._client = AsyncModbusTcpClient(host, port=port)
        self._lock = asyncio.Lock()

        # Manual power set-point requested via the Number entity. The AC
        # ELWA 2 reverts a Modbus power set-point to automatic control if it
        # is not refreshed periodically, so it is re-written on every poll
        # cycle while active (mirrors evcc's heartbeat behaviour). Register
        # 1000 is explicitly exempt from my-PV's "write at most once a day"
        # rule, so this is safe to do on every update.
        self.power_setpoint: int | None = None

        # Last non-zero power that was explicitly set (via the Power number
        # entity or the water heater's "on"), persisted to disk so it can be
        # restored both when switching the water heater back on after an
        # "off" and after a Home Assistant restart.
        self.last_power_setpoint: int | None = None
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY_LAST_POWER_SETPOINT}_{entry.entry_id}"
        )

    async def async_load_persisted_data(self) -> None:
        """Load the last manually set power value from disk, if any."""
        stored = await self._store.async_load()
        if stored is not None:
            self.last_power_setpoint = stored.get("last_power_setpoint")

    async def _async_ensure_connected(self) -> None:
        if not self._client.connected:
            await self._client.connect()
            if not self._client.connected:
                raise UpdateFailed(
                    f"Cannot connect to MyPV ELWA 2 at {self.host}:{self.port}"
                )

    async def _read_holding_registers(self, address: int, count: int) -> list[int]:
        try:
            result = await self._client.read_holding_registers(
                address, count=count, slave=self.unit_id
            )
        except TypeError:
            result = await self._client.read_holding_registers(
                address, count=count, device_id=self.unit_id
            )
        if result.isError():
            raise UpdateFailed(f"Modbus error reading register {address}: {result}")
        return result.registers

    async def _write_registers(self, address: int, values: list[int]) -> None:
        try:
            result = await self._client.write_registers(
                address, values, slave=self.unit_id
            )
        except TypeError:
            result = await self._client.write_registers(
                address, values, device_id=self.unit_id
            )
        if result.isError():
            raise UpdateFailed(f"Modbus error writing register {address}: {result}")

    async def async_set_power(self, watts: int) -> None:
        """Write a manual power set-point and keep re-asserting it.

        Non-zero values are remembered as `last_power_setpoint` and
        persisted to disk, so that e.g. the water heater's "on" can restore
        whatever power was last requested - including after a Home Assistant
        restart. Setting 0 (off) intentionally does not overwrite it.
        """
        watts = max(0, int(watts))
        async with self._lock:
            await self._async_ensure_connected()
            await self._write_registers(REG_POWER, [watts])
        self.power_setpoint = watts
        if watts > 0 and watts != self.last_power_setpoint:
            self.last_power_setpoint = watts
            await self._store.async_save({"last_power_setpoint": watts})
        await self.async_request_refresh()

    async def async_set_target_temperature(self, celsius: float) -> None:
        """Write the boost/target temperature set-point.

        Note: per my-PV's documentation this register must not be written
        more than once a day to protect the device's non-volatile memory, so
        avoid wiring this into automations that change it frequently.
        """
        raw = max(0, int(round(celsius * 10)))
        async with self._lock:
            await self._async_ensure_connected()
            await self._write_registers(REG_TARGET_TEMPERATURE, [raw])
        await self.async_request_refresh()

    async def _async_update_data(self) -> MyPVElwa2Data:
        async with self._lock:
            await self._async_ensure_connected()
            try:
                if self.power_setpoint is not None:
                    await self._write_registers(REG_POWER, [self.power_setpoint])
                registers = await self._read_holding_registers(REG_BASE, REG_COUNT)
            except (ModbusException, OSError) as err:
                raise UpdateFailed(f"Error communicating with device: {err}") from err

        def reg(address: int) -> int:
            return registers[address - REG_BASE]

        power = reg(REG_POWER)
        status_code = reg(REG_STATUS)
        relay_state = reg(REG_RELAY_STATE)

        return MyPVElwa2Data(
            power=power,
            temperature=reg(REG_TEMP_T1) / 10,
            temperature_2=reg(REG_TEMP_T2) / 10,
            target_temperature=reg(REG_TARGET_TEMPERATURE) / 10,
            status_code=status_code,
            operation_state=reg(REG_OPERATION_STATE),
            operation_mode=reg(REG_OPERATION_MODE),
            aux_relay_active=bool(relay_state & 0b01),
            selv_relay_active=bool(relay_state & 0b10),
            voltage=reg(REG_VOLTAGE),
            max_controlled_power=reg(REG_MAX_CONTROLLED_POWER),
            max_available_power=reg(REG_MAX_AVAILABLE_POWER),
            device_enabled=bool(reg(REG_DEVICE_STATE)),
            heating_active=status_code in HEATING_STATUS_CODES,
            serial_number=decode_serial_number(
                registers[
                    REG_SERIAL_NUMBER_BASE - REG_BASE : REG_SERIAL_NUMBER_BASE
                    - REG_BASE
                    + REG_SERIAL_NUMBER_COUNT
                ]
            ),
            # "e<main>.<sub>" for the controller firmware. The official
            # documentation's format hint ("exxxxxyy") is ambiguous about how
            # main/sub are meant to be zero-padded and joined, so this is a
            # readable best-effort rendering, not a claim to match my-PV's
            # own internal display format exactly.
            firmware_version=(
                f"e{reg(REG_CONTROLLER_FW_MAIN_VERSION)}."
                f"{reg(REG_CONTROLLER_FW_SUB_VERSION):02d}"
            ),
            # "ep%03d" / "ec%03d" are confirmed by the device's own HTTP
            # status page (data.jsn), which reports e.g. "psversion": "ep001"
            # and "coversion": "ec005" for these same values.
            powerstage_firmware_version=f"ep{reg(REG_POWERSTAGE_FW_VERSION):03d}",
            co_controller_firmware_version=f"ec{reg(REG_CO_CONTROLLER_FW_VERSION):03d}",
        )

    async def async_close(self) -> None:
        """Close the Modbus connection."""
        self._client.close()
