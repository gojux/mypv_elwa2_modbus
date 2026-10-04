"""Water heater platform for the MyPV ELWA 2 Modbus (unofficial) integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.water_heater import (
    STATE_ELECTRIC,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MAX_POWER, DEFAULT_MAX_POWER
from . import MyPVElwa2ConfigEntry
from .coordinator import MyPVElwa2ModbusCoordinator
from .entity import MyPVElwa2Entity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyPVElwa2ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the MyPV ELWA 2 water heater entity."""
    coordinator = entry.runtime_data
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
    survives a Home Assistant restart. Only manually requested values count:
    while automatic grid-surplus control is enabled, "on" restores nothing
    and lets that control start from the live surplus instead. The very
    first time it is ever turned on - before any power has been set - it
    falls back to the device's
    configured max. power (register 1014), or the max power configured in
    the integration's options if that isn't available yet. While on, the
    coordinator keeps re-asserting this value on every poll cycle (see
    `coordinator.power_setpoint`), since the AC ELWA 2 reverts an unrefreshed
    Modbus power set-point to automatic control after a timeout.

    "Off" writes 0 exactly once - unlike "on", it is then *not* re-asserted
    on every poll cycle, so Home Assistant doesn't keep fighting the
    device's own automatic PV-excess control while off.

    The on/off state itself is latched (`coordinator.is_on`), not derived
    fresh from the Status register on every poll: besides the explicit
    actions above, it can only change autonomously in two cases - it becomes
    "on" if the device starts heating (Status = Heat/Boost heat) while
    previously "off" (e.g. its own PV-excess control kicking in), and it
    becomes "off" if the device reports it has lost control or is disabled
    (Status = no_control/device_disabled). Normal Heat<->Standby cycling in
    between does not flip it back off by itself. See
    `coordinator._async_update_latch` for the exact rules.
    """

    _attr_name = None
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
        self._attr_operation_list = [STATE_OFF, STATE_ELECTRIC]
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
        """Return the current, latched operation mode (see class docstring)."""
        return STATE_ELECTRIC if self.coordinator.is_on else STATE_OFF

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature (writes register 1002)."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        _LOGGER.debug("Water heater: setting target temperature to %s°C", temperature)
        await self.coordinator.async_set_target_temperature(float(temperature))

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set a new operation mode."""
        _LOGGER.debug("Water heater: operation mode set to %s", operation_mode)
        if operation_mode == STATE_OFF:
            await self.async_turn_off()
        else:
            await self.async_turn_on()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the water heater on, restoring the last requested power.

        While automatic grid-surplus control is enabled, nothing is restored:
        the control derives the power from the live surplus instead.
        """
        if self.coordinator.auto_control_enabled:
            _LOGGER.debug("Water heater: turning on under automatic control")
            await self.coordinator.async_turn_on_auto_control()
            return
        if self.coordinator.last_power_setpoint:
            power = self.coordinator.last_power_setpoint
            source = "last_power_setpoint"
        else:
            data = self.coordinator.data
            if data is not None and data.max_controlled_power:
                power = data.max_controlled_power
                source = "device's max_controlled_power"
            else:
                power = self._fallback_max_power
                source = "configured fallback max power"
        _LOGGER.debug(
            "Water heater: turning on, requesting %s W (source: %s)", power, source
        )
        await self.coordinator.async_set_power(power)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the water heater off (writes 0 W to the Power register)."""
        _LOGGER.debug("Water heater: turning off")
        await self.coordinator.async_set_power(0)
