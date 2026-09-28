"""Number platform for the MyPV ELWA 2 Modbus (unofficial) integration."""

from __future__ import annotations

import logging

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfPower, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_MAX_POWER,
    DEFAULT_MAX_POWER,
    DOMAIN,
    FALLBACK_AUTO_MAX_POWER_WATTS,
    MAX_AUTO_RATE_LIMIT_SECONDS,
    MAX_AUTO_RESERVE_WATTS,
    MAX_AUTO_SMOOTHING_SECONDS,
    MIN_AUTO_RATE_LIMIT_SECONDS,
    MIN_AUTO_SMOOTHING_SECONDS,
)
from .coordinator import MyPVElwa2ModbusCoordinator
from .entity import MyPVElwa2Entity

_LOGGER = logging.getLogger(__name__)


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
            MyPVElwa2AutoReserveNumber(coordinator),
            MyPVElwa2AutoMaxPowerNumber(coordinator),
            MyPVElwa2AutoRateLimitNumber(coordinator),
            MyPVElwa2AutoSmoothingNumber(coordinator),
        ]
    )


class MyPVElwa2PowerNumber(MyPVElwa2Entity, NumberEntity):
    """Writable power set-point.

    This entity does not exist in the official my-PV app/integration, which
    only allows setting a target temperature. Writing directly to the power
    register enables e.g. direct control from an energy management system.

    The displayed value is the value we ourselves last commanded
    (`coordinator.power_setpoint`), not necessarily the device's live power
    reading - this avoids UI flicker from momentary mismatches between what
    was just written and what the next poll reads back. See
    `coordinator.async_set_manual_power`.

    Setting this to 0 W does *not* turn the water heater off - the
    relationship between the two is one-directional: turning the water
    heater off does bring this down to 0 W (since it then shows 0 while
    `is_on` is False), but setting 0 W here only reduces the output, it
    does not flip the water heater to "off". Setting a value > 0 does turn
    the water heater on if it wasn't already.

    While automatic grid-surplus control is enabled (see the "Auto control"
    switch), manual changes here are ignored - the automatic controller
    keeps writing its own calculated value, and this entity just reflects
    it, same as when a manual value is active.
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
        """Return the currently commanded power (optimistic, see class docstring)."""
        if self.coordinator.power_setpoint is not None:
            return float(self.coordinator.power_setpoint)
        if not self.coordinator.is_on:
            return 0.0
        if self.coordinator.data is not None:
            return float(self.coordinator.data.power)
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Write a new power level to the device, unless auto control is active."""
        if self.coordinator.auto_control_enabled:
            _LOGGER.debug(
                "Power number: ignoring manual set to %s W, automatic control is active",
                value,
            )
            return
        await self.coordinator.async_set_manual_power(int(value))


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


class MyPVElwa2AutoReserveNumber(MyPVElwa2Entity, NumberEntity):
    """Grid-surplus reserve that automatic control always leaves unused.

    E.g. a reserve of 100 W means automatic control aims to keep 100 W of
    surplus flowing to the grid rather than consuming every last watt, as a
    safety margin against overshooting into grid import.
    """

    _attr_translation_key = "auto_reserve"
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_min_value = 0
    _attr_native_max_value = MAX_AUTO_RESERVE_WATTS
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: MyPVElwa2ModbusCoordinator) -> None:
        """Initialize the auto-control reserve number entity."""
        super().__init__(coordinator, "auto_reserve")

    @property
    def native_value(self) -> float:
        """Return the configured reserve."""
        return float(self.coordinator.auto_reserve_watts)

    async def async_set_native_value(self, value: float) -> None:
        """Set a new reserve."""
        await self.coordinator.async_set_auto_reserve(int(value))


class MyPVElwa2AutoMaxPowerNumber(MyPVElwa2Entity, NumberEntity):
    """Upper power limit that automatic control may request."""

    _attr_translation_key = "auto_max_power"
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: MyPVElwa2ModbusCoordinator) -> None:
        """Initialize the auto-control max. power number entity."""
        super().__init__(coordinator, "auto_max_power")

    @property
    def native_max_value(self) -> float:
        """Return the ceiling, preferring the device-reported limit."""
        data = self.coordinator.data
        if data is not None and data.max_controlled_power:
            return float(data.max_controlled_power)
        return float(FALLBACK_AUTO_MAX_POWER_WATTS)

    @property
    def native_value(self) -> float:
        """Return the configured max. power for automatic control."""
        return float(self.coordinator.auto_max_power_watts)

    async def async_set_native_value(self, value: float) -> None:
        """Set a new max. power for automatic control."""
        await self.coordinator.async_set_auto_max_power(int(value))


class MyPVElwa2AutoRateLimitNumber(MyPVElwa2Entity, NumberEntity):
    """Minimum time between two automatic-control writes."""

    _attr_translation_key = "auto_rate_limit"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_native_min_value = MIN_AUTO_RATE_LIMIT_SECONDS
    _attr_native_max_value = MAX_AUTO_RATE_LIMIT_SECONDS
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: MyPVElwa2ModbusCoordinator) -> None:
        """Initialize the auto-control rate limit number entity."""
        super().__init__(coordinator, "auto_rate_limit")

    @property
    def native_value(self) -> float:
        """Return the configured rate limit."""
        return float(self.coordinator.auto_rate_limit_seconds)

    async def async_set_native_value(self, value: float) -> None:
        """Set a new rate limit."""
        await self.coordinator.async_set_auto_rate_limit(int(value))


class MyPVElwa2AutoSmoothingNumber(MyPVElwa2Entity, NumberEntity):
    """Moving-average smoothing window applied to the grid power entity.

    0 disables smoothing entirely (the raw sensor value is used as-is).
    See `coordinator._compute_smoothed_grid_power` for the exact formula.
    """

    _attr_translation_key = "auto_smoothing"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_native_min_value = MIN_AUTO_SMOOTHING_SECONDS
    _attr_native_max_value = MAX_AUTO_SMOOTHING_SECONDS
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: MyPVElwa2ModbusCoordinator) -> None:
        """Initialize the auto-control smoothing number entity."""
        super().__init__(coordinator, "auto_smoothing")

    @property
    def native_value(self) -> float:
        """Return the configured smoothing window."""
        return float(self.coordinator.auto_smoothing_seconds)

    async def async_set_native_value(self, value: float) -> None:
        """Set a new smoothing window."""
        await self.coordinator.async_set_auto_smoothing(int(value))
