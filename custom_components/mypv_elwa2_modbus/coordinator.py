"""DataUpdateCoordinator for the MyPV ELWA 2 Modbus (unofficial) integration."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_AUTO_RATE_LIMIT_SECONDS,
    DEFAULT_AUTO_RESERVE_WATTS,
    DEFAULT_AUTO_SMOOTHING_SECONDS,
    FALLBACK_AUTO_MAX_POWER_WATTS,
    HEATING_STATUS_CODES,
    LATCH_DEBOUNCE_POLLS,
    MAX_AUTO_RATE_LIMIT_SECONDS,
    MAX_AUTO_RESERVE_WATTS,
    MAX_AUTO_SMOOTHING_SECONDS,
    MIN_AUTO_RATE_LIMIT_SECONDS,
    MIN_AUTO_SMOOTHING_SECONDS,
    NO_CONTROL_STATUS_CODES,
    REG_BASE,
    REG_CO_CONTROLLER_FW_VERSION,
    REG_CONTROLLER_FW_MAIN_VERSION,
    REG_CONTROLLER_FW_SUB_VERSION,
    REG_COUNT,
    REG_DEVICE_STATE,
    REG_MAX_AVAILABLE_POWER,
    REG_MAX_CONTROLLED_POWER,
    REG_OPERATION_MODE,
    REG_OPERATION_STATE,
    REG_POWER,
    REG_POWERSTAGE_FW_VERSION,
    REG_RELAY_STATE,
    REG_SERIAL_NUMBER_BASE,
    REG_SERIAL_NUMBER_COUNT,
    REG_STATUS,
    REG_TARGET_TEMPERATURE,
    REG_TEMP_T1,
    REG_TEMP_T2,
    REG_VOLTAGE,
    STORAGE_KEY_LAST_POWER_SETPOINT,
    STORAGE_VERSION,
)
from .util import decode_serial_number

_LOGGER = logging.getLogger(__name__)


def _monotonic_clock() -> float:
    """Return the clock used to measure the time between successful polls.

    Kept as a module-level function so tests can replace only this clock.
    Patching `time.monotonic` itself would also change the event loop's
    timers, which is what made the earlier freezer-based test hang.
    """
    return time.monotonic()


@dataclass
class MyPVElwa2Data:
    """A single snapshot of AC ELWA 2 Modbus data."""

    power: int
    temperature: float
    temperature_2: float
    target_temperature: float
    status_code: int
    operation_state: int
    operation_mode: int
    aux_relay_active: bool
    selv_relay_active: bool
    voltage: int
    max_controlled_power: int
    max_available_power: int
    device_enabled: bool
    heating_active: bool
    serial_number: str
    firmware_version: str
    powerstage_firmware_version: str
    co_controller_firmware_version: str


class MyPVElwa2ModbusCoordinator(DataUpdateCoordinator[MyPVElwa2Data]):
    """Poll an AC ELWA 2 over Modbus TCP and keep manual power set-points alive."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        entry: ConfigEntry,
        host: str,
        port: int,
        unit_id: int,
        scan_interval: int,
        grid_power_entity_id: str | None = None,
        invert_grid_power_sign: bool = False,
        default_max_power: int = FALLBACK_AUTO_MAX_POWER_WATTS,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.entry = entry
        self.host = host
        self.port = port
        self.unit_id = unit_id
        # The device's serial number (set as the config entry's unique ID
        # during the config/reconfigure flow) is used as the stable device
        # identifier, independent of host/port, so that changing the IP
        # address later (Reconfigure) does not create new entities.
        self.unique_id = entry.unique_id or f"{host}_{port}_{unit_id}"
        self.device_name = entry.title

        self._client = AsyncModbusTcpClient(host, port=port)
        self._lock = asyncio.Lock()

        # Manual power set-point that is actively re-asserted every poll
        # cycle (mirrors evcc's heartbeat behaviour, since the AC ELWA 2
        # reverts an unrefreshed Modbus power set-point to automatic control
        # after a timeout). Register 1000 is explicitly exempt from my-PV's
        # "write at most once a day" rule, so this is safe to do on every
        # update. None means "not actively driving the device" (off): while
        # off, this integration intentionally stops writing to register
        # 1000 on every cycle, to avoid fighting the device's own automatic
        # PV-excess control (see async_set_power / _async_update_latch).
        self.power_setpoint: int | None = None

        # Last non-zero power that was explicitly set (via the Power number
        # entity or the water heater's "on"), so it can be restored when
        # switching the water heater back on after an "off".
        self.last_power_setpoint: int | None = None

        # Latched on/off state shown by the water heater / power number
        # entities. Latched rather than derived directly from the live
        # Status register on every poll, so that normal Heat<->Standby
        # cycling (e.g. due to fluctuating PV excess) does not flicker the
        # displayed state - see _async_update_latch().
        self.is_on: bool = False

        # Consecutive polls that have observed NO_CONTROL_STATUS_CODES /
        # HEATING_STATUS_CODES in a row, used to debounce the auto-off /
        # auto-on detection in _async_update_latch symmetrically (see
        # LATCH_DEBOUNCE_POLLS). Both are reset on every explicit action
        # (async_set_power), since an explicit action always wins over a
        # stale streak from before it.
        self._no_control_streak: int = 0
        self._heating_streak: int = 0

        # Automatic grid-surplus power control. When enabled (and the water
        # heater is "on"), every change of `grid_power_entity_id` triggers a
        # new power calculation instead of waiting for the next poll cycle -
        # see _async_grid_power_listener / _async_apply_auto_control.
        self._grid_power_entity_id = grid_power_entity_id
        self._invert_grid_power_sign = invert_grid_power_sign
        self.auto_control_enabled: bool = False
        self.auto_reserve_watts: int = DEFAULT_AUTO_RESERVE_WATTS
        # Defaults to the configured max_power option; overridden below by
        # any previously persisted value once async_load_persisted_data runs.
        self.auto_max_power_watts: int = default_max_power
        self.auto_rate_limit_seconds: int = DEFAULT_AUTO_RATE_LIMIT_SECONDS
        self._auto_control_last_write: datetime | None = None
        self._auto_control_lock = asyncio.Lock()

        # Moving-average smoothing window (s) applied to the grid power
        # entity before it enters the calculation; 0 disables smoothing.
        # See _compute_smoothed_grid_power.
        self.auto_smoothing_seconds: int = DEFAULT_AUTO_SMOOTHING_SECONDS
        self._grid_power_samples: deque[tuple[datetime, float]] = deque()

        # Measured time between the last two successful polls, in seconds.
        # None after a failed poll or on the first poll, because no interval
        # is known then. Used by the energy sensor, so it never extrapolates
        # over an outage and counts poll timing that differs from the scan
        # interval (e.g. immediate refreshes after a user action).
        self._last_poll_time: float | None = None
        self.poll_interval_s: float | None = None

        # Raw register block of the last successful read, for diagnostics.
        self.last_registers: list[int] | None = None

        # All of the above are persisted to disk so they survive a Home
        # Assistant restart (see async_load_persisted_data / _async_persist_state).
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY_LAST_POWER_SETPOINT}_{entry.entry_id}"
        )

    async def async_load_persisted_data(self) -> None:
        """Load the last manually set power value and on/off state from disk."""
        stored = await self._store.async_load()
        if stored is not None:
            self.last_power_setpoint = stored.get("last_power_setpoint")
            self.is_on = bool(stored.get("is_on", False))
            self.auto_control_enabled = bool(stored.get("auto_control_enabled", False))
            self.auto_reserve_watts = int(
                stored.get("auto_reserve_watts", DEFAULT_AUTO_RESERVE_WATTS)
            )
            self.auto_max_power_watts = int(
                stored.get("auto_max_power_watts", self.auto_max_power_watts)
            )
            self.auto_rate_limit_seconds = int(
                stored.get("auto_rate_limit_seconds", DEFAULT_AUTO_RATE_LIMIT_SECONDS)
            )
            self.auto_smoothing_seconds = int(
                stored.get("auto_smoothing_seconds", DEFAULT_AUTO_SMOOTHING_SECONDS)
            )

    async def _async_persist_state(self) -> None:
        """Persist the on/off and automatic-control state to disk."""
        await self._store.async_save(
            {
                "last_power_setpoint": self.last_power_setpoint,
                "is_on": self.is_on,
                "auto_control_enabled": self.auto_control_enabled,
                "auto_reserve_watts": self.auto_reserve_watts,
                "auto_max_power_watts": self.auto_max_power_watts,
                "auto_rate_limit_seconds": self.auto_rate_limit_seconds,
                "auto_smoothing_seconds": self.auto_smoothing_seconds,
            }
        )

    def async_setup_grid_listener(self) -> None:
        """Start listening for changes of the configured grid power entity."""
        if not self._grid_power_entity_id:
            return
        unsub = async_track_state_change_event(
            self.hass, [self._grid_power_entity_id], self._async_grid_power_listener
        )
        self.entry.async_on_unload(unsub)

    async def _async_ensure_connected(self) -> None:
        if not self._client.connected:
            await self._client.connect()
            if not self._client.connected:
                raise UpdateFailed(
                    f"Cannot connect to MyPV ELWA 2 at {self.host}:{self.port}"
                )

    def _reset_connection(self) -> None:
        """Force-close the Modbus connection so the next call reconnects.

        pymodbus's `client.connected` does not always reliably reflect a
        stale/dead TCP connection (e.g. after the device's own Modbus server
        silently drops it, or a NAT/router in between times it out).
        Without this, `_async_ensure_connected` would see `connected` still
        True and keep retrying against the same broken connection every poll
        cycle indefinitely - which looks like sensors "freezing" at their
        last successfully-read value, since a failed poll leaves
        `coordinator.data` untouched.
        """
        _LOGGER.debug(
            "Resetting Modbus connection to %s:%s after a communication error",
            self.host,
            self.port,
        )
        self._client.close()

    async def _read_holding_registers(self, address: int, count: int) -> list[int]:
        result = await self._client.read_holding_registers(
            address, count=count, device_id=self.unit_id
        )
        if result.isError():
            raise UpdateFailed(f"Modbus error reading register {address}: {result}")
        _LOGGER.debug(
            "Read from %s:%s: %s",
            self.host,
            self.port,
            dict(zip(range(address, address + count), result.registers, strict=False)),
        )
        return result.registers

    async def _write_registers(self, address: int, values: list[int]) -> None:
        result = await self._client.write_registers(
            address, values, device_id=self.unit_id
        )
        if result.isError():
            raise UpdateFailed(f"Modbus error writing register {address}: {result}")
        _LOGGER.debug(
            "Wrote to %s:%s: %s",
            self.host,
            self.port,
            dict(zip(range(address, address + len(values)), values, strict=False)),
        )

    async def _async_write_power_register(self, watts: int) -> None:
        """Write register 1000, resetting the connection on any I/O error."""
        async with self._lock:
            await self._async_ensure_connected()
            try:
                await self._write_registers(REG_POWER, [watts])
            except (ModbusException, OSError) as err:
                self._reset_connection()
                raise UpdateFailed(f"Error communicating with device: {err}") from err

    async def async_set_power(self, watts: int) -> None:
        """Turn the water heater on (watts > 0) or off (watts == 0).

        This is the *only* way (besides autonomous Status detection, see
        `_async_update_latch`) that `is_on` changes - it is used exclusively
        by the water heater entity's on/off, *not* by the Power number
        entity anymore (see `async_set_manual_power`): the relationship
        between the two is one-directional. Turning the water heater off
        always brings the Power number down to 0 (via `is_on` becoming
        False, see its `native_value`), but setting the Power number to 0
        must NOT turn the water heater off - only `async_set_manual_power`
        handles that side.

        `watts > 0` is treated as "on": the value is written once, then kept
        alive by being re-asserted every poll cycle, and remembered as
        `last_power_setpoint` (persisted, so the water heater's "on" can
        restore it later - including after a Home Assistant restart).

        `watts == 0` is treated as "off": 0 is written exactly once. Unlike
        the "on" case, this integration then stops writing to register 1000
        on every poll cycle while off, so it doesn't keep fighting any
        automatic PV-excess control the device performs on its own.
        `last_power_setpoint` is intentionally left untouched so the target
        power is remembered for the next "on".

        Note that turning the water heater off does *not* disable the "Auto
        control" switch itself - it only pauses the underlying function
        (see `_async_apply_auto_control`'s `not self.is_on` guard). If the
        switch is still on, automatic control resumes by itself as soon as
        the water heater is turned back on, without needing to be
        re-enabled.
        """
        watts = max(0, int(watts))
        await self._async_write_power_register(watts)
        if watts > 0:
            self.power_setpoint = watts
            self.last_power_setpoint = watts
            self.is_on = True
        else:
            self.power_setpoint = None
            self.is_on = False
        # An explicit action always wins over auto-detection in either
        # direction: reset both debounce streaks so a stale streak from
        # before this call (or the device's Status register lagging behind
        # the write we just made, in *either* direction) can't immediately
        # undo it on the next poll(s).
        self._no_control_streak = 0
        self._heating_streak = 0
        await self._async_persist_state()
        await self.async_request_refresh()

    async def async_set_manual_power(self, watts: int) -> None:
        """Write a power level from the Power number entity.

        Unlike `async_set_power` (water heater on/off), setting this to
        0 W does *not* turn the water heater off - it only reduces the
        output to 0 W while `is_on` stays whatever it already was, exactly
        like automatic control's 0 W handling (see `_async_write_auto_power`).
        If the water heater is already off, a request for 0 W is a no-op
        (there is nothing to reduce, and register 1000 is already 0).

        Setting a value > 0 *does* turn the water heater on if it wasn't
        already - the one-directional relationship only concerns the "0 W /
        off" case, not the "on" case.
        """
        watts = max(0, int(watts))
        if watts == 0 and not self.is_on:
            return
        await self._async_write_power_register(watts)
        self.power_setpoint = watts
        if watts > 0:
            self.last_power_setpoint = watts
            if not self.is_on:
                self.is_on = True
                self._no_control_streak = 0
                self._heating_streak = 0
        await self._async_persist_state()
        await self.async_request_refresh()

    async def async_set_device_enabled(self, enabled: bool) -> None:
        """Enable or disable the device itself (register 1081).

        Unlike REG_POWER, this is written exactly once per explicit call and
        is *never* re-asserted on a poll cycle: per my-PV's documentation,
        register 1081 must not be written more than once a day to protect
        the device's non-volatile memory. This is meant for occasional,
        manual control (a Switch entity) - do not wire it into automations
        that could toggle it frequently.
        """
        value = 1 if enabled else 0
        async with self._lock:
            await self._async_ensure_connected()
            try:
                await self._write_registers(REG_DEVICE_STATE, [value])
            except (ModbusException, OSError) as err:
                self._reset_connection()
                raise UpdateFailed(f"Error communicating with device: {err}") from err
        await self.async_request_refresh()

    async def async_set_target_temperature(self, celsius: float) -> None:
        """Write the boost/target temperature set-point.

        Note: per my-PV's documentation this register must not be written
        more than once a day to protect the device's non-volatile memory, so
        avoid wiring this into automations that change it frequently.
        """
        raw = max(0, round(celsius * 10))
        async with self._lock:
            await self._async_ensure_connected()
            try:
                await self._write_registers(REG_TARGET_TEMPERATURE, [raw])
            except (ModbusException, OSError) as err:
                self._reset_connection()
                raise UpdateFailed(f"Error communicating with device: {err}") from err
        await self.async_request_refresh()

    async def async_set_auto_control_enabled(self, enabled: bool) -> None:
        """Enable or disable automatic grid-surplus power control.

        This is a standing preference, independent of the water heater's
        current on/off state: it can be turned on while the water heater
        happens to be off right now, and simply stays paused (does nothing)
        until the water heater is turned on - see
        `_async_apply_auto_control`'s `not self.is_on` guard. Turning the
        water heater off later does not turn this switch off either; it
        only pauses the function again.

        Turning it on still requires a grid power entity to be configured
        (Options), so the switch never silently does nothing for a reason
        that isn't obviously fixable from the water heater itself.
        """
        if enabled and not self._grid_power_entity_id:
            raise HomeAssistantError(
                "Configure a grid power entity in the integration's options"
                " before enabling automatic control"
            )
        self.auto_control_enabled = enabled
        await self._async_persist_state()
        if enabled and self.is_on:
            # Apply right away instead of waiting for the next grid sensor change.
            await self._async_apply_auto_control(
                self._async_current_grid_state(), bypass_rate_limit=True
            )
        self.async_update_listeners()

    async def async_turn_on_auto_control(self) -> None:
        """Turn on while automatic control is enabled.

        No stored power is restored here: the automatic control starts from
        the device's current power and the live grid surplus instead, so the
        heater does not jump to an old value first and correct itself later.
        """
        self.is_on = True
        self.power_setpoint = None
        self._no_control_streak = 0
        self._heating_streak = 0
        await self._async_persist_state()
        # The calculation starts from the device's actual power. After a
        # recent "off", coordinator.data can still hold the pre-off value
        # because a refresh is debounced, so read the device first.
        await self.async_refresh()
        await self._async_apply_auto_control(
            self._async_current_grid_state(), bypass_rate_limit=True
        )

    def _async_current_grid_state(self) -> State | None:
        """Return the current state of the grid power entity, if configured."""
        if not self._grid_power_entity_id:
            return None
        return self.hass.states.get(self._grid_power_entity_id)

    # The setters clamp to the same limits as the Number entities, so a
    # service call or a future caller cannot bypass them.

    async def async_set_auto_reserve(self, watts: int) -> None:
        """Set the grid-surplus reserve (W) automatic control always leaves unused."""
        self.auto_reserve_watts = min(max(0, int(watts)), MAX_AUTO_RESERVE_WATTS)
        await self._async_persist_state()
        self.async_update_listeners()

    async def async_set_auto_max_power(self, watts: int) -> None:
        """Set the upper power limit (W) automatic control may request."""
        self.auto_max_power_watts = min(max(0, int(watts)), FALLBACK_AUTO_MAX_POWER_WATTS)
        await self._async_persist_state()
        self.async_update_listeners()

    async def async_set_auto_rate_limit(self, seconds: int) -> None:
        """Set the minimum time (s) between two automatic-control writes."""
        self.auto_rate_limit_seconds = min(
            max(MIN_AUTO_RATE_LIMIT_SECONDS, int(seconds)), MAX_AUTO_RATE_LIMIT_SECONDS
        )
        await self._async_persist_state()
        self.async_update_listeners()

    async def async_set_auto_smoothing(self, seconds: int) -> None:
        """Set the moving-average smoothing window (s); 0 disables it."""
        self.auto_smoothing_seconds = min(
            max(MIN_AUTO_SMOOTHING_SECONDS, int(seconds)), MAX_AUTO_SMOOTHING_SECONDS
        )
        self._grid_power_samples.clear()
        await self._async_persist_state()
        self.async_update_listeners()

    def _compute_smoothed_grid_power(self, raw_value: float, now: datetime) -> float:
        """Smooth the (already sign-corrected) raw grid power value.

        Result = min(moving_average(raw_value over auto_smoothing_seconds),
        raw_value), compared as signed numbers (never absolute value) - so
        e.g. -10 counts as smaller than -5. The moving average smooths out
        brief spikes in surplus so the ELWA doesn't needlessly readjust for
        them; the min() then makes sure a sudden *drop* in surplus (or a
        swing into grid import) is still acted on immediately, since in
        that case the average - not yet caught up - would otherwise be
        higher than reality and make automatic control overconsume.
        """
        if self.auto_smoothing_seconds <= 0:
            self._grid_power_samples.clear()
            return raw_value

        self._grid_power_samples.append((now, raw_value))
        cutoff = now - timedelta(seconds=self.auto_smoothing_seconds)
        while self._grid_power_samples and self._grid_power_samples[0][0] < cutoff:
            self._grid_power_samples.popleft()

        average = sum(value for _, value in self._grid_power_samples) / len(
            self._grid_power_samples
        )
        return min(average, raw_value)

    @callback
    def _async_grid_power_listener(self, event: Event) -> None:
        """Schedule handling of a grid power entity state change."""
        new_state: State | None = event.data["new_state"]
        self.hass.async_create_task(self._async_auto_control_from_event(new_state))

    async def _async_auto_control_from_event(self, grid_state: State | None) -> None:
        """Run automatic control for a grid event, logging instead of raising.

        A failed write must not end up as an unhandled task exception. The
        rate limit is rolled back in that case (see _async_apply_auto_control),
        so the next grid event retries.
        """
        try:
            await self._async_apply_auto_control(grid_state)
        except UpdateFailed as err:
            _LOGGER.warning("Automatic power control could not write to the device: %s", err)

    async def _async_apply_auto_control(
        self, grid_state: State | None, *, bypass_rate_limit: bool = False
    ) -> None:
        """Recompute and write a new power set-point from the grid sensor.

        Formula: new_power = current_power + grid_surplus - reserve, clamped
        to [0, auto_max_power_watts] (and the device's own max_controlled_power,
        if reported). This is a simple proportional zero-export-with-headroom
        controller: whatever surplus is currently measured at the grid
        connection (which already reflects the ELWA's own consumption) is
        added to the current set-point, minus the configured reserve, so the
        loop converges towards leaving exactly `auto_reserve_watts` of
        surplus unused. `grid_surplus` here is the smoothed value from
        `_compute_smoothed_grid_power`, not the raw sensor reading.

        The whole calculation runs under `_auto_control_lock`. Otherwise a
        second grid event that waits for the Modbus lock longer than the rate
        limit could read a stale base and overwrite the first write.
        """
        if grid_state is None or grid_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        try:
            raw_grid_power = float(grid_state.state)
        except (TypeError, ValueError):
            _LOGGER.debug(
                "Auto control: could not parse grid power state %r", grid_state.state
            )
            return
        # The sign inversion (if configured) is applied first, so both the
        # smoothing history and the min() comparison already work with the
        # same sign convention as the rest of the calculation.
        if self._invert_grid_power_sign:
            raw_grid_power = -raw_grid_power

        async with self._auto_control_lock:
            # Checked under the lock: the water heater may have been turned
            # off or automatic control disabled while this call was waiting.
            if not self.auto_control_enabled or not self.is_on:
                return

            now = dt_util.utcnow()
            grid_power = self._compute_smoothed_grid_power(raw_grid_power, now)

            if (
                not bypass_rate_limit
                and self._auto_control_last_write is not None
                and (now - self._auto_control_last_write).total_seconds()
                < self.auto_rate_limit_seconds
            ):
                return

            base = self.power_setpoint
            if base is None:
                base = self.data.power if self.data is not None else 0

            max_power = self.auto_max_power_watts
            if self.data is not None and self.data.max_controlled_power:
                max_power = min(max_power, self.data.max_controlled_power)

            new_power = base + grid_power - self.auto_reserve_watts
            new_power = max(0, min(round(new_power), max_power))

            previous_write = self._auto_control_last_write
            self._auto_control_last_write = now
            _LOGGER.debug(
                "Auto control: grid_raw=%.1f W, grid_smoothed=%.1f W, reserve=%s W,"
                " base=%s W -> new power=%s W",
                raw_grid_power,
                grid_power,
                self.auto_reserve_watts,
                base,
                new_power,
            )
            try:
                await self._async_write_auto_power(new_power)
            except UpdateFailed:
                # The timestamp only marks a successful write. Roll it back, so
                # a failed write does not block the next attempt for the rate limit.
                self._auto_control_last_write = previous_write
                raise

    async def _async_write_auto_power(self, watts: int) -> None:
        """Write a power set-point computed by automatic control.

        Unlike `async_set_power` (used for explicit user on/off actions),
        this never turns the water heater off or disables automatic control
        just because the calculated value happens to be 0 W - e.g. "no
        surplus right now" is a perfectly normal, transient output level
        while automatic control keeps running and watching for surplus to
        return. It also skips the full `async_request_refresh()` (a fresh
        Modbus read of all registers) that `async_set_power` triggers, since
        that would be wasteful if the grid entity updates frequently -
        entities are instead updated locally via `async_update_listeners()`.

        It deliberately does not touch `last_power_setpoint`: that value
        is the last *manually* requested power, which "on" restores when
        automatic control is disabled. Automatic values are transient and
        must not replace it. For the same reason nothing needs persisting here.
        """
        await self._async_write_power_register(watts)
        self.power_setpoint = watts
        self.async_update_listeners()

    async def _async_update_latch(self, status_code: int) -> None:
        """Update the latched on/off state from an autonomously observed Status.

        The water heater's "on" state is latched rather than derived fresh
        from the Status register on every poll: once on, normal Heat<->
        Standby cycling (e.g. due to fluctuating PV excess) must not flip it
        back off by itself, or the displayed state (and the Power number's
        commanded value) would flicker. It can only become:
        - "off": through an explicit Home Assistant action (see
          async_set_power), or autonomously when the device reports it has
          lost control / is disabled (NO_CONTROL_STATUS_CODES) for at least
          LATCH_DEBOUNCE_POLLS polls in a row.
        - "on": through an explicit Home Assistant action, or autonomously
          when the device starts heating (HEATING_STATUS_CODES) for at least
          LATCH_DEBOUNCE_POLLS polls in a row while it was previously
          considered off - e.g. the device's own automatic PV-excess control
          kicking in without Home Assistant's involvement.

        The debounce is applied symmetrically in both directions, because
        the device does not update its Status register instantly after a
        Power write in *either* direction: the poll triggered right after an
        explicit "on" typically still observes the previous "no_control"
        status for a moment, and the poll right after an explicit "off"
        typically still observes the previous "heat"/"boost_heat" status for
        a moment. Without the debounce, that very refresh would immediately
        undo whichever action was just requested.
        """
        if status_code in NO_CONTROL_STATUS_CODES:
            self._heating_streak = 0
            self._no_control_streak += 1
            if self._no_control_streak >= LATCH_DEBOUNCE_POLLS and (
                self.is_on or self.power_setpoint is not None
            ):
                self.is_on = False
                self.power_setpoint = None
                # The "Auto control" switch itself is left untouched here -
                # only the underlying function pauses while is_on is False
                # (see _async_apply_auto_control's guard). It resumes by
                # itself once is_on becomes True again.
                await self._async_persist_state()
        elif status_code in HEATING_STATUS_CODES:
            self._no_control_streak = 0
            self._heating_streak += 1
            if self._heating_streak >= LATCH_DEBOUNCE_POLLS and not self.is_on:
                self.is_on = True
                await self._async_persist_state()
        else:
            # standby, heat_finished, legionella boost, blocked, faults, ...
            self._no_control_streak = 0
            self._heating_streak = 0

    async def _async_update_data(self) -> MyPVElwa2Data:
        async with self._lock:
            await self._async_ensure_connected()
            try:
                if self.power_setpoint is not None:
                    await self._write_registers(REG_POWER, [self.power_setpoint])
                registers = await self._read_holding_registers(REG_BASE, REG_COUNT)
            except (ModbusException, OSError) as err:
                self._reset_connection()
                raise UpdateFailed(f"Error communicating with device: {err}") from err

        # Measured right after the successful read, so this interval ends
        # at the moment the power value below was observed.
        now = _monotonic_clock()
        previous = self._last_poll_time if self.last_update_success else None
        self._last_poll_time = now
        self.poll_interval_s = None if previous is None else now - previous
        self.last_registers = list(registers)

        def reg(address: int) -> int:
            return registers[address - REG_BASE]

        power = reg(REG_POWER)
        status_code = reg(REG_STATUS)
        relay_state = reg(REG_RELAY_STATE)

        await self._async_update_latch(status_code)

        return MyPVElwa2Data(
            power=power,
            temperature=reg(REG_TEMP_T1) / 10,
            temperature_2=reg(REG_TEMP_T2) / 10,
            target_temperature=reg(REG_TARGET_TEMPERATURE) / 10,
            status_code=status_code,
            operation_state=reg(REG_OPERATION_STATE),
            operation_mode=reg(REG_OPERATION_MODE),
            aux_relay_active=bool(relay_state & 0b01),
            selv_relay_active=bool(relay_state & 0b10),
            voltage=reg(REG_VOLTAGE),
            max_controlled_power=reg(REG_MAX_CONTROLLED_POWER),
            max_available_power=reg(REG_MAX_AVAILABLE_POWER),
            device_enabled=bool(reg(REG_DEVICE_STATE)),
            heating_active=status_code in HEATING_STATUS_CODES,
            serial_number=decode_serial_number(
                registers[
                    REG_SERIAL_NUMBER_BASE - REG_BASE : REG_SERIAL_NUMBER_BASE
                    - REG_BASE
                    + REG_SERIAL_NUMBER_COUNT
                ]
            ),
            # "e<main>.<sub>" for the controller firmware. The official
            # documentation's format hint ("exxxxxyy") is ambiguous about how
            # main/sub are meant to be zero-padded and joined, so this is a
            # readable best-effort rendering, not a claim to match my-PV's
            # own internal display format exactly.
            firmware_version=(
                f"e{reg(REG_CONTROLLER_FW_MAIN_VERSION)}."
                f"{reg(REG_CONTROLLER_FW_SUB_VERSION):02d}"
            ),
            # "ep%03d" / "ec%03d" are confirmed by the device's own HTTP
            # status page (data.jsn), which reports e.g. "psversion": "ep001"
            # and "coversion": "ec005" for these same values.
            powerstage_firmware_version=f"ep{reg(REG_POWERSTAGE_FW_VERSION):03d}",
            co_controller_firmware_version=f"ec{reg(REG_CO_CONTROLLER_FW_VERSION):03d}",
        )

    async def async_close(self) -> None:
        """Close the Modbus connection."""
        self._client.close()
