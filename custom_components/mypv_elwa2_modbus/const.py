"""Constants for the MyPV ELWA 2 Modbus (unofficial) integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "mypv_elwa2_modbus"

MANUFACTURER: Final = "my-PV"
MODEL: Final = "AC ELWA 2"

# Config / options keys
CONF_UNIT_ID: Final = "unit_id"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_MAX_POWER: Final = "max_power"
CONF_GRID_POWER_ENTITY_ID: Final = "grid_power_entity_id"
CONF_INVERT_GRID_POWER_SIGN: Final = "invert_grid_power_sign"

DEFAULT_PORT: Final = 502
DEFAULT_UNIT_ID: Final = 1
DEFAULT_SCAN_INTERVAL: Final = 5  # seconds
DEFAULT_MAX_POWER: Final = 3000  # W, fallback if the device does not report a limit
DEFAULT_INVERT_GRID_POWER_SIGN: Final = False

MIN_SCAN_INTERVAL: Final = 2
MAX_SCAN_INTERVAL: Final = 300

# Automatic grid-surplus power control (see coordinator._async_apply_auto_control).
# Defaults for the runtime-adjustable Number entities backing it.
DEFAULT_AUTO_RESERVE_WATTS: Final = 100  # W of surplus always left unused
DEFAULT_AUTO_RATE_LIMIT_SECONDS: Final = 1  # minimum time between two auto-control writes
MIN_AUTO_RATE_LIMIT_SECONDS: Final = 1
MAX_AUTO_RATE_LIMIT_SECONDS: Final = 3600
MAX_AUTO_RESERVE_WATTS: Final = 10000
FALLBACK_AUTO_MAX_POWER_WATTS: Final = 10000  # ceiling if the device reports no limit

# Moving-average smoothing window (s) applied to the grid power entity
# before it enters the auto-control calculation. 0 disables smoothing.
DEFAULT_AUTO_SMOOTHING_SECONDS: Final = 5
MIN_AUTO_SMOOTHING_SECONDS: Final = 0
MAX_AUTO_SMOOTHING_SECONDS: Final = 300

# Persistent storage (.storage/<key>_<entry_id>) for the last manually set,
# non-zero power value, so it survives Home Assistant restarts.
STORAGE_VERSION: Final = 1
STORAGE_KEY_LAST_POWER_SETPOINT: Final = f"{DOMAIN}.last_power_setpoint"

# Modbus holding register map for the AC ELWA 2.
#
# Sourced from my-PV's official "AC ELWA 2 - Documentation of Controls"
# (Version 241205), download.my-pv.com/acelwa2/AC_ELWA_2_Documentation-Controls_EN241205.pdf
# Cross-checked against https://github.com/evcc-io/evcc/blob/master/charger/mypv.go
# (production-tested against real AC ELWA 2 devices).
#
# Registers that exist on other my-PV devices (e.g. AC THOR's "load state" at
# 1059, or a third temperature sensor at 1031) are intentionally NOT read
# here, since the official AC ELWA 2 documentation does not define them for
# this device.
#
# All registers below are read with a single FC03 "Read Holding Registers"
# call spanning REG_BASE..REG_BASE+REG_COUNT-1, which is what makes this
# integration noticeably faster than polling the device's HTTP/JSON API.
REG_BASE: Final = 1000
REG_COUNT: Final = 87  # covers registers 1000 through 1086 inclusive

REG_POWER: Final = 1000  # Power (W), read/write. Safe to write frequently.
REG_TEMP_T1: Final = 1001  # Temp 1, internal sensor, raw value = °C * 10
REG_TARGET_TEMPERATURE: Final = 1002  # Tmax, target temp (solar), raw = °C * 10
REG_STATUS: Final = 1003  # Status, see STATUS_CODES
REG_MAX_CONTROLLED_POWER: Final = 1014  # max Power, configured limit (W), 500-3500
REG_CONTROLLER_FW_MAIN_VERSION: Final = 1016  # Controller firmware main version
REG_POWERSTAGE_FW_VERSION: Final = 1017  # Powerstage firmware version, format "ep%03d"
REG_TEMP_T2: Final = 1030  # Temp 2, external sensor, raw value = °C * 10
REG_CONTROLLER_FW_SUB_VERSION: Final = 1028  # Controller firmware sub version
REG_RELAY_STATE: Final = 1058  # Relay status bitmask: bit0 AUX, bit1 SELV
REG_VOLTAGE: Final = 1061  # U L1 (V), power stage input voltage
REG_OPERATION_MODE: Final = 1065  # Operation mode: 1 or 3, see DEVICE_OPERATION_MODES
REG_MAX_AVAILABLE_POWER: Final = 1071  # Pmax_abs, max. power currently possible (W)
REG_OPERATION_STATE: Final = 1077  # operation state, see OPERATION_STATES
REG_DEVICE_STATE: Final = 1081  # Device state: 0 = disabled, 1 = enabled (inferred, see README)
REG_CO_CONTROLLER_FW_VERSION: Final = 1086  # Co-Controller firmware version, format "ec%03d"

# NOTE: the official documentation does not define a hardware/board revision
# register or a MAC address register anywhere for the AC ELWA 2 (the UDP
# device-discovery reply it documents only carries the IP address, serial
# number, firmware version and ELWA number - no MAC either), so neither can
# be read over Modbus and this integration does not expose them.

# AC ELWA 2 serial number, 2 ASCII characters per register (16 chars total).
# Used as the config entry's unique ID so that the IP address/port can be
# changed later (Reconfigure) without losing entity history, since it does
# not depend on the network address. Already covered by the REG_BASE /
# REG_COUNT bulk read above.
REG_SERIAL_NUMBER_BASE: Final = 1018
REG_SERIAL_NUMBER_COUNT: Final = 8

# IMPORTANT: per the official documentation, all writable registers must NOT
# be written more than once a day to protect the device's non-volatile
# memory, EXCEPT for registers 1000, 1009, 1010, 1011, 1012 and 1078-1080.
# REG_DEVICE_STATE (1081) is *not* in that exception list. It is exposed as a
# Switch entity for occasional, explicit manual control (see
# coordinator.async_set_device_enabled), but - unlike REG_POWER - is
# intentionally never re-asserted automatically on a poll cycle, so normal
# use stays well within "at most once a day".

# REG_STATUS (1003) values, verbatim from the official documentation.
STATUS_CODES: Final[dict[int, str]] = {
    1: "no_control",
    2: "heat",
    3: "standby",
    4: "boost_heat",
    5: "heat_finished",
    20: "legionella_boost_active",
    21: "device_disabled",
    22: "device_blocked",
    201: "stl_triggered",
    202: "power_stage_overtemp",
    203: "power_stage_pcb_temp_probe_fault",
    204: "hardware_fault",
    205: "elwa_temp_sensor_fault",
    209: "mainboard_error",
}

# Status codes under which the AC ELWA 2 is actively heating.
HEATING_STATUS_CODES: Final = frozenset({2, 4})

# Status codes under which the AC ELWA 2 has lost control / is disabled -
# these force the WaterHeater's latched on/off state (see coordinator.py) to
# off, even if it was previously considered on.
NO_CONTROL_STATUS_CODES: Final = frozenset({1, 21})  # no_control, device_disabled

# Number of consecutive polls that must observe the *opposite* condition
# before the latch actually flips - applied symmetrically to both
# directions: NO_CONTROL_STATUS_CODES before flipping to off, and
# HEATING_STATUS_CODES before flipping to on. Needed because the device does
# not update its Status register instantly after a Power write: the poll
# triggered right after an explicit "on" typically still reads the previous
# ("no_control") status, and the poll right after an explicit "off"
# typically still reads the previous ("heat"/"boost_heat") status. Without
# this debounce, the very refresh triggered by either action would
# immediately undo it. See coordinator._async_update_latch.
LATCH_DEBOUNCE_POLLS: Final = 2

# REG_OPERATION_STATE (1077) values, mapped from the official documentation's
# "operation states (screen icon)" footnote:
#   0 green tick flashes        -> standby, waiting for PV excess
#   1 yellow wave on             -> heating with PV excess
#   2 yellow wave flashes        -> boost backup mode
#   3 green tick + yellow wave   -> target temperature reached while heating
#   4 red cross on                -> no control signal
#   5 red cross flashes           -> no control signal (intermittent)
#   6 block active                -> blocked
OPERATION_STATES: Final[dict[int, str]] = {
    0: "standby",
    1: "pv_excess",
    2: "boost_backup",
    3: "target_reached",
    4: "no_control_signal",
    5: "no_control_signal_intermittent",
    6: "blocked",
}

# REG_OPERATION_MODE (1065) values, from the official documentation:
# Mode 1 = ELWA only, power range 0-3500 W.
# Mode 3 = ELWA + AUX relay, power range 0-6500 W.
DEVICE_OPERATION_MODES: Final[dict[int, str]] = {
    1: "mode_1",
    3: "mode_3",
}

