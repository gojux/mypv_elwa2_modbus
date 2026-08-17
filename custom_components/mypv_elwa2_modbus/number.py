"""Number platform for the MyPV ELWA 2 Modbus (unofficial) integration."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfTemperature
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
    """Set up MyPV ELWA 2 Modbus number entities."""
    coordinator: MyPVElwa2ModbusCoordinator = hass.data[DOMAIN][entry.entry_id]
    max_power = entry.options.get(CONF_MAX_POWER, DEFAULT_MAX_POWER)

    async_add_entities(
        [
            MyPVElwa2PowerNumber(coordinator, max_power),
            MyPVElwa2TargetTemperatureNumber(coordinator),
        ]
    )


class MyPVElwa2PowerNumber(MyPVElwa2Entity, NumberEntity):
    """Writable power set-point.

    This entity does not exist in the official my-PV app/integration, which
    only allows setting a target temperature. Writing directly to the power
    register enables e.g. direct control from an energy management system.
    """

    _attr_translation_key = "power"
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: MyPVElwa2ModbusCoordinator, max_power: int) -> None:
        """Initialize the power number entity."""
        super().__init__(coordinator, "power_setpoint")
        self._fallback_max_power = max_power

    @property
    def native_max_value(self) -> float:
        """Return the maximum power, preferring the device-reported limit."""
        data = self.coordinator.data
        if data is not None and data.max_controlled_power:
            return float(data.max_controlled_power)
        return float(self._fallback_max_power)

    @property
    def native_value(self) -> float | None:
        """Return the current power set-point."""
        if self.coordinator.data is None:
            return None
        return float(self.coordinator.data.power)

    async def async_set_native_value(self, value: float) -> None:
        """Write a new power set-point to the device."""
        await self.coordinator.async_set_power(int(value))


class MyPVElwa2TargetTemperatureNumber(MyPVElwa2Entity, NumberEntity):
    """Writable boost/target temperature set-point."""

    _attr_translation_key = "target_temperature"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 0
    _attr_native_max_value = 85
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: MyPVElwa2ModbusCoordinator) -> None:
        """Initialize the target temperature number entity."""
        super().__init__(coordinator, "target_temperature")

    @property
    def native_value(self) -> float | None:
        """Return the current target temperature."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.target_temperature

    async def async_set_native_value(self, value: float) -> None:
        """Write a new target temperature to the device."""
        await self.coordinator.async_set_target_temperature(value)
