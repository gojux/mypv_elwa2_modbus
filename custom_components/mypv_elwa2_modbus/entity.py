"""Base entity for the MyPV ELWA 2 Modbus (unofficial) integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import MyPVElwa2ModbusCoordinator


class MyPVElwa2Entity(CoordinatorEntity[MyPVElwa2ModbusCoordinator]):
    """Base class for all MyPV ELWA 2 Modbus entities."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: MyPVElwa2ModbusCoordinator, unique_id_suffix: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.unique_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=coordinator.device_name,
            # coordinator.unique_id *is* the device's serial number (read
            # via Modbus during the config/reconfigure flow, see
            # config_flow.py), so this is available immediately without
            # depending on the coordinator having fetched live data yet.
            # Shown by Home Assistant in the device info panel.
            serial_number=coordinator.unique_id,
            # Controller firmware version. By the time entities are set up,
            # coordinator.data is always populated (async_setup_entry awaits
            # the first refresh first), but the None-check is kept as a
            # defensive fallback. There is no hardware/board revision or MAC
            # address register documented for the AC ELWA 2, so hw_version
            # and connections are intentionally left unset.
            sw_version=coordinator.data.firmware_version if coordinator.data else None,
            configuration_url=f"http://{coordinator.host}",
        )
