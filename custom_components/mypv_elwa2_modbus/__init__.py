"""The MyPV ELWA 2 Modbus (unofficial) integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

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
)
from .coordinator import MyPVElwa2ModbusCoordinator

_LOGGER = logging.getLogger(__name__)

type MyPVElwa2ConfigEntry = ConfigEntry[MyPVElwa2ModbusCoordinator]

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.WATER_HEATER,
]


async def async_setup_entry(hass: HomeAssistant, entry: MyPVElwa2ConfigEntry) -> bool:
    """Set up MyPV ELWA 2 Modbus (unofficial) from a config entry."""
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = MyPVElwa2ModbusCoordinator(
        hass,
        entry=entry,
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        unit_id=entry.data.get(CONF_UNIT_ID, DEFAULT_UNIT_ID),
        scan_interval=scan_interval,
        grid_power_entity_id=entry.options.get(CONF_GRID_POWER_ENTITY_ID),
        invert_grid_power_sign=entry.options.get(
            CONF_INVERT_GRID_POWER_SIGN, DEFAULT_INVERT_GRID_POWER_SIGN
        ),
        default_max_power=entry.options.get(CONF_MAX_POWER, DEFAULT_MAX_POWER),
    )
    await coordinator.async_load_persisted_data()
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_setup_grid_listener()

    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: MyPVElwa2ConfigEntry) -> None:
    """Reload the config entry when its options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: MyPVElwa2ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_close()
    return unload_ok
