"""Water heater platform for the MyPV ELWA 2 Modbus (unofficial) integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.water_heater import (
    STATE_ELECTRIC,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MAX_POWER, DEFAULT_MAX_POWER, DOMAIN
from .coordinator import MyPVElwa2ModbusCoordinator
from .entity import MyPVElwa2Entity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the MyPV ELWA 2 water heater entity."""
    coordinator: MyPVElwa2ModbusCoordinator = hass.data[DOMAIN][entry.entry_id]
    max_power = entry.options.get(CONF_MAX_POWER, DEFAULT_MAX_POWER)
    async_add_entities([MyPVElwa2WaterHeater(coordinator, max_power)])


class MyPVElwa2WaterHeater(MyPVElwa2Entity, WaterHeaterEntity):
    """Represents the AC ELWA 2 as a water heater, mirroring the official app.

    On/off is intentionally implemented via the Power register (1000), the
    same register the Power number entity uses, and NOT via the device's own
    "Boost activate" register (1012): boost mode makes the AC ELWA 2 heat
    electrically at full power regardless of available PV excess, which is
    not what an on/off toggle should do. Writing to the Power register
    instead simply requests a power level from the device - if a higher-level
    PV-excess controller (e.g. this integration's Power number entity, or an
    external EMS) continuously adjusts it, PV excess is respected; a static
    "on" here is a plain power request like evcc's `Enable()` for this
    device, not a forced boost.

    "On" restores the last non-zero power that was explicitly requested
    (`coordinator.last_power_setpoint`, e.g. via the Power number entity or a
    previous "on") to register 1000. This is persisted to disk, so it also
    survives a Home Assistant restart. The very first time it is ever turned
    on - before any power has been set - it falls back to the device's
    configured max. power (register 1014), or the max power configured in
    the integration's options if that isn't available yet.

    "Off" writes 0. This is the same register the AC ELWA 2 reverts to
    automatic control if it isn't refreshed periodically, so the coordinator
    re-asserts an active set-point on every poll cycle (see
    `coordinator.power_setpoint`).
    """

    _attr_name = None
    _attr_operation_list = [STATE_OFF, STATE_ELECTRIC]
    _attr_supported_features = (
        WaterHeaterEntityFeature.ON_OFF
        | WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 0
    _attr_max_temp = 85
    _attr_target_temperature_step = 1

    def __init__(self, coordinator: MyPVElwa2ModbusCoordinator, max_power: int) -> None:
        """Initialize the water heater entity."""
        super().__init__(coordinator, "water_heater")
        self._fallback_max_power = max_power

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature, read from sensor T1."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.temperature

    @property
    def target_temperature(self) -> float | None:
        """Return the target/boost temperature (register 1002)."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.target_temperature

    @property
    def current_operation(self) -> str:
        """Return the current operation mode, based on the Status register."""
        data = self.coordinator.data
        if data is not None and data.heating_active:
            return STATE_ELECTRIC
        return STATE_OFF

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature (writes register 1002)."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        await self.coordinator.async_set_target_temperature(float(temperature))

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set a new operation mode."""
        if operation_mode == STATE_OFF:
            await self.async_turn_off()
        else:
            await self.async_turn_on()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the water heater on, restoring the last requested power."""
        if self.coordinator.last_power_setpoint:
            power = self.coordinator.last_power_setpoint
        else:
            data = self.coordinator.data
            power = (
                data.max_controlled_power
                if data is not None and data.max_controlled_power
                else self._fallback_max_power
            )
        await self.coordinator.async_set_power(power)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the water heater off (writes 0 W to the Power register)."""
        await self.coordinator.async_set_power(0)
