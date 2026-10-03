"""Switch platform for the MyPV ELWA 2 Modbus (unofficial) integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MyPVElwa2ConfigEntry
from .coordinator import MyPVElwa2ModbusCoordinator
from .entity import MyPVElwa2Entity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyPVElwa2ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MyPV ELWA 2 Modbus switch entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        [MyPVElwa2DeviceEnabledSwitch(coordinator), MyPVElwa2AutoControlSwitch(coordinator)]
    )


class MyPVElwa2DeviceEnabledSwitch(MyPVElwa2Entity, SwitchEntity):
    """Explicit control of the device's own enabled/disabled state.

    This writes register 1081 ("Device state" / the device's own "devmode"
    flag, see README), which is a different concept from the water heater's
    on/off: the water heater only requests a power level via register 1000
    while leaving the device itself enabled, whereas this switch disables
    the AC ELWA 2 entirely - equivalent to disabling it in the device's own
    web interface.

    Per my-PV's documentation this register must not be written more than
    once a day to protect the device's non-volatile memory. Unlike register
    1000, it is therefore intentionally *never* re-asserted automatically on
    a poll cycle - only this entity's own explicit on/off actions write to
    it. Use it for occasional, manual control only; avoid automations that
    would toggle it frequently.

    This replaces the previous read-only "Device enabled" diagnostic binary
    sensor, which showed the same register but could not change it.
    """

    _attr_translation_key = "device_enabled"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: MyPVElwa2ModbusCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "device_enabled")

    @property
    def is_on(self) -> bool | None:
        """Return true if the device is enabled."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.device_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the device."""
        await self.coordinator.async_set_device_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the device."""
        await self.coordinator.async_set_device_enabled(False)


class MyPVElwa2AutoControlSwitch(MyPVElwa2Entity, SwitchEntity):
    """Enable/disable automatic grid-surplus power control.

    While on, the Power number entity's manual input is ignored: the
    coordinator instead reacts to changes of the configured grid power
    entity (see the integration's options) and writes its own calculated
    power value, aiming to leave the configured "Auto control reserve" of
    surplus unused (see number.py).

    This switch reflects a standing preference, independent of the water
    heater's on/off state: turning the water heater off does *not* turn
    this off - it only pauses the underlying function (no power writes)
    for as long as the water heater is off. Turning the water heater back
    on resumes automatic control by itself, without needing to flip this
    switch again. This state is persisted, so it survives a Home Assistant
    restart.
    """

    _attr_translation_key = "auto_control"

    def __init__(self, coordinator: MyPVElwa2ModbusCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "auto_control")

    @property
    def is_on(self) -> bool:
        """Return true if automatic grid-surplus control is enabled."""
        return self.coordinator.auto_control_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable automatic grid-surplus power control."""
        await self.coordinator.async_set_auto_control_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable automatic grid-surplus power control."""
        await self.coordinator.async_set_auto_control_enabled(False)
