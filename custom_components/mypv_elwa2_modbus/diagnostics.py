"""Diagnostics download for the MyPV ELWA 2 Modbus (unofficial) integration.

The download contains the raw holding register block of the last successful
read, annotated with the register names from const.py. It is meant to verify
the register map against the device, e.g. by comparing the values with what
my-PV's own app shows.

Host and serial number are redacted. The serial number is also stored in the
raw registers 1018-1025 (ASCII, two characters per register), so those are
redacted too.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import MyPVElwa2ConfigEntry
from . import const

_SERIAL_ADDRESSES = range(
    const.REG_SERIAL_NUMBER_BASE,
    const.REG_SERIAL_NUMBER_BASE + const.REG_SERIAL_NUMBER_COUNT,
)
REDACTED_KEYS = {
    CONF_HOST,
    "serial_number",
    *(str(address) for address in _SERIAL_ADDRESSES),
}

# Constants that describe the read block rather than a single register.
_NOT_A_REGISTER = {"REG_BASE", "REG_COUNT", "REG_SERIAL_NUMBER_COUNT"}

# Maps register address -> constant name, e.g. 1000 -> "REG_POWER".
REGISTER_NAMES: dict[int, str] = {
    value: name
    for name, value in vars(const).items()
    if name.startswith("REG_") and name not in _NOT_A_REGISTER and isinstance(value, int)
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MyPVElwa2ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data

    registers: dict[str, dict[str, Any]] | None = None
    if coordinator.last_registers is not None:
        registers = {
            str(const.REG_BASE + offset): {
                "name": REGISTER_NAMES.get(const.REG_BASE + offset, ""),
                "value": value,
            }
            for offset, value in enumerate(coordinator.last_registers)
        }

    diagnostics = {
        "entry": {"data": dict(entry.data), "options": dict(entry.options)},
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "poll_interval_s": coordinator.poll_interval_s,
            "power_setpoint": coordinator.power_setpoint,
            "last_power_setpoint": coordinator.last_power_setpoint,
            "is_on": coordinator.is_on,
            "auto_control_enabled": coordinator.auto_control_enabled,
            "auto_reserve_watts": coordinator.auto_reserve_watts,
            "auto_max_power_watts": coordinator.auto_max_power_watts,
            "auto_rate_limit_seconds": coordinator.auto_rate_limit_seconds,
            "auto_smoothing_seconds": coordinator.auto_smoothing_seconds,
        },
        "parsed_data": asdict(coordinator.data) if coordinator.data is not None else None,
        "registers": registers,
    }
    return async_redact_data(diagnostics, REDACTED_KEYS)
