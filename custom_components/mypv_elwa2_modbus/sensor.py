"""Sensor platform for the MyPV ELWA 2 Modbus (unofficial) integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_OPERATION_MODES, OPERATION_STATES, STATUS_CODES
from . import MyPVElwa2ConfigEntry
from .coordinator import MyPVElwa2Data, MyPVElwa2ModbusCoordinator
from .entity import MyPVElwa2Entity
from .util import integrate_energy_kwh


@dataclass(frozen=True, kw_only=True)
class MyPVElwa2SensorEntityDescription(SensorEntityDescription):
    """Describes a MyPV ELWA 2 sensor entity."""

    value_fn: Callable[[MyPVElwa2Data], Any]


SENSOR_DESCRIPTIONS: tuple[MyPVElwa2SensorEntityDescription, ...] = (
    MyPVElwa2SensorEntityDescription(
        key="power",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.power,
    ),
    MyPVElwa2SensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: data.temperature,
    ),
    MyPVElwa2SensorEntityDescription(
        key="temperature_2",
        translation_key="temperature_2",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.temperature_2,
    ),
    MyPVElwa2SensorEntityDescription(
        key="voltage",
        translation_key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.voltage,
    ),
    MyPVElwa2SensorEntityDescription(
        key="operation_state",
        translation_key="operation_state",
        device_class=SensorDeviceClass.ENUM,
        options=list(OPERATION_STATES.values()),
        value_fn=lambda data: OPERATION_STATES.get(
            data.operation_state, f"unknown_{data.operation_state}"
        ),
    ),
    MyPVElwa2SensorEntityDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=list(STATUS_CODES.values()),
        value_fn=lambda data: STATUS_CODES.get(
            data.status_code, f"unknown_{data.status_code}"
        ),
    ),
    MyPVElwa2SensorEntityDescription(
        key="operation_mode",
        translation_key="operation_mode",
        device_class=SensorDeviceClass.ENUM,
        options=list(DEVICE_OPERATION_MODES.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: DEVICE_OPERATION_MODES.get(
            data.operation_mode, f"unknown_{data.operation_mode}"
        ),
    ),
    MyPVElwa2SensorEntityDescription(
        key="max_controlled_power",
        translation_key="max_controlled_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.max_controlled_power,
    ),
    MyPVElwa2SensorEntityDescription(
        key="max_available_power",
        translation_key="max_available_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.max_available_power,
    ),
    MyPVElwa2SensorEntityDescription(
        key="serial_number",
        translation_key="serial_number",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.serial_number,
    ),
    MyPVElwa2SensorEntityDescription(
        key="firmware_version",
        translation_key="firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.firmware_version,
    ),
    MyPVElwa2SensorEntityDescription(
        key="powerstage_firmware_version",
        translation_key="powerstage_firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.powerstage_firmware_version,
    ),
    MyPVElwa2SensorEntityDescription(
        key="co_controller_firmware_version",
        translation_key="co_controller_firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.co_controller_firmware_version,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyPVElwa2ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MyPV ELWA 2 Modbus sensors."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = [
        MyPVElwa2Sensor(coordinator, description) for description in SENSOR_DESCRIPTIONS
    ]
    # The Energy sensor is not part of the official my-PV app/integration;
    # it is derived locally by integrating the Power reading over time.
    entities.append(MyPVElwa2EnergySensor(coordinator))

    async_add_entities(entities)


class MyPVElwa2Sensor(MyPVElwa2Entity, SensorEntity):
    """A read-only MyPV ELWA 2 sensor backed by a Modbus register."""

    entity_description: MyPVElwa2SensorEntityDescription

    def __init__(
        self,
        coordinator: MyPVElwa2ModbusCoordinator,
        description: MyPVElwa2SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the current value of the sensor."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class MyPVElwa2EnergySensor(MyPVElwa2Entity, RestoreSensor, SensorEntity):
    """Energy sensor, integrated locally from the Power register.

    The AC ELWA 2 does not expose a cumulative energy register over Modbus,
    so this sensor keeps its own running total (Wh -> kWh) by integrating the
    power reading over the measured time between successful polls, similar to
    the HA "Riemann sum integral" helper, and restores it across restarts.
    """

    _attr_translation_key = "energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator: MyPVElwa2ModbusCoordinator) -> None:
        """Initialize the energy sensor."""
        super().__init__(coordinator, "energy")
        self._total_kwh: float = 0.0
        self._last_data: MyPVElwa2Data | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last known total when the entity is added."""
        await super().async_added_to_hass()
        last_sensor_data = await self.async_get_last_sensor_data()
        if last_sensor_data is not None and last_sensor_data.native_value is not None:
            try:
                self._total_kwh = float(last_sensor_data.native_value)
            except (TypeError, ValueError):
                self._total_kwh = 0.0

    @callback
    def _handle_coordinator_update(self) -> None:
        """Integrate the energy of each new successful poll.

        Only a new data snapshot counts. Manual coordinator updates, e.g. after
        an automatic-control write, reuse the same snapshot and add nothing.
        The interval is the time the coordinator measured between two
        successful polls. After a failed poll the coordinator has no interval,
        so the next successful poll only starts a new run and the last known
        power is never extrapolated over an outage.
        """
        data = self.coordinator.data
        if (
            data is not None
            and self.coordinator.last_update_success
            and data is not self._last_data
        ):
            self._last_data = data
            if self.coordinator.poll_interval_s is not None:
                self._total_kwh = integrate_energy_kwh(
                    self._total_kwh,
                    data.power,
                    self.coordinator.poll_interval_s,
                )
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float:
        """Return the accumulated energy in kWh."""
        return round(self._total_kwh, 4)
