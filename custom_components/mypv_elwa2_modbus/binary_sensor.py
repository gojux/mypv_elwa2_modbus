"""Binary sensor platform for the MyPV ELWA 2 Modbus (unofficial) integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MyPVElwa2Data, MyPVElwa2ModbusCoordinator
from .entity import MyPVElwa2Entity


@dataclass(frozen=True, kw_only=True)
class MyPVElwa2BinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a MyPV ELWA 2 binary sensor entity."""

    value_fn: Callable[[MyPVElwa2Data], bool | None]


BINARY_SENSOR_DESCRIPTIONS: tuple[MyPVElwa2BinarySensorEntityDescription, ...] = (
    MyPVElwa2BinarySensorEntityDescription(
        key="heating_active",
        translation_key="heating_active",
        value_fn=lambda data: data.heating_active,
    ),
    MyPVElwa2BinarySensorEntityDescription(
        key="aux_relay_active",
        translation_key="aux_relay_active",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.aux_relay_active,
    ),
    MyPVElwa2BinarySensorEntityDescription(
        key="selv_relay_active",
        translation_key="selv_relay_active",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.selv_relay_active,
    ),
    # "device_enabled" used to be a read-only diagnostic here; it is now a
    # controllable Switch entity instead (see switch.py), since register
    # 1081 can be written manually to explicitly enable/disable the device.
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MyPV ELWA 2 Modbus binary sensors."""
    coordinator: MyPVElwa2ModbusCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MyPVElwa2BinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class MyPVElwa2BinarySensor(MyPVElwa2Entity, BinarySensorEntity):
    """A MyPV ELWA 2 binary sensor backed by a Modbus register."""

    entity_description: MyPVElwa2BinarySensorEntityDescription

    def __init__(
        self,
        coordinator: MyPVElwa2ModbusCoordinator,
        description: MyPVElwa2BinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
