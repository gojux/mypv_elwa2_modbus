# MyPV ELWA 2 Modbus (unofficial)

[🇩🇪 Deutsch](README.md) · 🇬🇧 English

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gojux&repository=mypv_elwa2_modbus&category=integration)

An **unofficial** Home Assistant integration for the [my-PV AC ELWA 2](https://www.my-pv.com/) that communicates directly with the device via **Modbus TCP** – without going through the device's web API.

> ⚠️ This integration is not affiliated with my-PV GmbH and is neither supported nor maintained by my-PV. Use at your own risk, especially when writing registers (see [note on write frequency](#important-note-write-frequency-of-registers)).

## Why this integration?

There is already an [official Home Assistant integration by my-PV](https://github.com/my-PV/home-assistant-integration). This integration was developed anyway, because:

- **Modbus is significantly faster than HTTP/JSON.** The official integration talks to the device's web API and polls via HTTP/JSON every 5 seconds. This integration reads all relevant registers in **a single Modbus request** (registers 1000–1086), and can therefore update noticeably more often with lower latency and less overhead.
- **The official app/integration lacks features that are added here:**
  - An **energy sensor** (kWh) that is integrated locally from the power measurement and survives restarts – the official integration only provides instantaneous power, but no energy counter that can be used e.g. in the Home Assistant Energy dashboard.
  - A **writable power entity (number)** that lets you set the output power directly in watts – the official app/integration only allows setting a target temperature, not writing power directly. This is useful e.g. for direct control by an energy management system.

## Supported devices

Tested and developed for the **my-PV AC ELWA 2**. Other my-PV devices (AC THOR, ELWA-E, …) use partly different register addresses and are currently not supported by this integration.

## Requirements

- Home Assistant **2026.5** or newer.
- AC ELWA 2 on the same network as Home Assistant.
- **Modbus TCP must be enabled on the device:** enable it in the device's web interface under *Settings → Interfaces → Modbus*. The default port is `502`, the default unit ID is `1`.

## Installation

### Via HACS (recommended)

1. Click the badge above, or open HACS → *Custom repositories* → add this repository as type *Integration*.
2. Install "MyPV ELWA 2 Modbus (unofficial)".
3. Restart Home Assistant.

### Manual

1. Copy the folder `custom_components/mypv_elwa2_modbus` into the `config/custom_components/` directory of your Home Assistant installation.
2. Restart Home Assistant.

## Setup (config flow)

1. *Settings → Devices & services → Add integration*.
2. Select "MyPV ELWA 2 Modbus (unofficial)".
3. Enter the host/IP address, port (default `502`) and Modbus unit ID (default `1`).

The integration options additionally let you set the **poll interval** (default 5 s), a **fallback maximum power** for the power number entity, and – optionally – a **grid feed-in entity** for the [automatic control](#automatic-grid-feed-in-control). If your grid feed-in entity uses the opposite sign convention, also enable **"Invert sign of the grid feed-in entity"**.

### Changing IP address/port later (reconfigure)

If the device's IP address or port has changed (e.g. because no DHCP reservation is set up), you can update the configured device at any time without setting it up again:

1. *Settings → Devices & services → MyPV ELWA 2 Modbus (unofficial)*.
2. On the device, open the menu (⋮) and choose **"Reconfigure"**.
3. Enter the new host/IP address, port or unit ID.

The integration reads the device's **serial number** (registers 1018–1025) and uses it – not the IP address – as the unique device ID. Changing the IP address therefore neither changes the `entity_id`s nor discards history/customizations of existing entities. If the new address points to a device with a **different** serial number, the process aborts with an error for safety, instead of accidentally attaching the entities to another device.

## Entities

| Platform | Entity | Description |
|---|---|---|
| Sensor | Power | Current output power (W) |
| Sensor | **Energy** ⭐ | Locally integrated energy (kWh), stored across restarts – **not part of the official integration** |
| Sensor | Temperature / Temperature 2 | Internal (T1) and external (T2) temperature sensor (°C) |
| Sensor | Voltage | Mains voltage (V, diagnostic) |
| Sensor | Status | Detailed device status (heating / standby / boost heating / error codes …) |
| Sensor | Operation state | Operating state as shown by the display icon (standby / PV surplus / boost backup / target temperature reached / no control signal / blocked) |
| Sensor | Operation mode | Configured mode (mode 1: ELWA only up to 3.5 kW / mode 3: ELWA + AUX relay up to 6.5 kW; diagnostic, disabled by default) |
| Sensor | Max. configured power / Max. power currently possible | Power limits (diagnostic, disabled by default) |
| Sensor | Serial number | Serial number of the device (diagnostic); also used as the unique device ID for the reconfigure flow and shown directly in the device info panel |
| Sensor | Firmware version | Controller firmware version (diagnostic); also shown directly in the device info panel |
| Sensor | Firmware version (power stage) / (co-controller) | Firmware versions of the power stage and co-controller assemblies (diagnostic, disabled by default) |
| Binary sensor | Heating active | Device is currently heating (status = heat / boost heat) |
| Binary sensor | AUX relay active / SELV relay active | Relay status (diagnostic) |
| Number | **Power** ⭐ | Set the output power directly in watts – **not part of the official integration** |
| Number | Target temperature | Set the target/boost temperature (analogous to the water temperature setting in the official app) |
| Number | **Auto control reserve** ⭐ | Surplus (W) that automatic control should always leave untouched (default 100 W) |
| Number | **Auto control max. power** ⭐ | Upper limit (W) up to which automatic control may regulate |
| Number | **Auto control rate limit** ⭐ | Minimum interval (s) between two write operations of automatic control (default 1 s) |
| Number | **Auto control smoothing** ⭐ | Smoothing period (s) for the grid feed-in sensor, `0`–`300`, default 5 s (`0` = off) |
| Switch | **Device enabled** ⭐ | Enable/disable the device itself (register 1081, see below) – **not part of the official integration** |
| Switch | **Auto control** ⭐ | Enable/disable automatic grid feed-in control – **not part of the official integration** |
| Water heater | ELWA 2 | Current temperature (T1), target temperature, and on (`electric`) / off – like in the official app |

⭐ = additional functionality that goes beyond the scope of the official my-PV app/integration.

### Optimistic caching: power number and water heater entity

Setpoint and on/off state could "jump back and forth" with a purely live-register-based display – e.g. because the `Status` code normally alternates between "Heat"/"Boost heat" and "Standby" when PV surplus fluctuates, or because right after a write the live reading does not yet show the value that was just set. This integration avoids that with two mechanisms:

**1. The power number entity shows the commanded value, not the live measured value.** As long as we actively drive a setpoint, the entity shows exactly that value (`coordinator.power_setpoint`) instead of the live reading of register `1000`. If the ELWA is off, `0` is shown. If the device heats autonomously (see point 2), the entity shows the live reading, since no own setpoint is active in that case.

**2. The on/off state of the water heater entity is a "latch"**, not a direct reflection of the status register:

- **On** (`electric`) is set by: an explicit action in Home Assistant (water heater "on" or power number > 0 W), **or** automatically detected when the device switches from "off" to a heating status (status code "Heat" or "Boost heat") – e.g. when the device's own automatic PV surplus control starts heating by itself without Home Assistant having written anything.
- **Off** is set **only** by: an explicit action in Home Assistant (water heater "off"), **or** automatically detected when the device reports "no control signal" (`no_control`) or "disabled" (`device_disabled`).
- Normal alternation between "Heat" and "Standby" during operation does **not** change the on/off state – so no flickering occurs.

**The coupling between the power number and the water heater entity is deliberately one-directional:** water heater "off" sets the power number display to `0` (since it falls back to the off state without an active setpoint). Conversely, manually setting the power number to `0` does **not** switch the water heater off – it only reduces the power to `0 W` while "on" remains, just like a `0 W` value calculated by automatic control (see [automatic grid feed-in control](#automatic-grid-feed-in-control)). A positive value on the power number does switch the water heater on if it was off.

**No continuous writing in the off state:** While "on", the integration writes the power setpoint to register `1000` again on every poll cycle, as before (heartbeat, see below) – this also applies when the setpoint is `0 W`. While "off", `0` is written exactly once at the transition, and afterwards – until the next explicit action – nothing further is written to register `1000`, so that Home Assistant does not continuously override any automatic PV surplus control of the device.

On/off switching still works via the same **power register (`1000`)** that the power number entity uses (on: last set power value or fallback to the maximum power; off via the water heater entity: `0`; setting the power number to `0` does not switch off) – analogous to the `Enable()` implementation in [evcc](https://github.com/evcc-io/evcc/blob/master/charger/mypv.go). The device's own register `1012` ("Boost activate", physical boost backup button or `/control.html?boost=1`) is deliberately **not** used, because it ignores PV surplus and heats at full power.

### Restoring after a Home Assistant restart

Both the **last set power value** (any value > 0 W set via the power number or water heater) and the **on/off state** are stored in Home Assistant's local storage (`.storage/`) and restored on startup. A restart during operation therefore does not cause the water heater entity to wrongly fall back to "off", even if the device happens to be in its normal standby between two heating phases at the moment of the restart. Switching off deliberately does not overwrite the remembered power value.

## Automatic grid feed-in control

Instead of calculating and setting the power via your own automation, the integration can itself react to changes of a grid feed-in sensor and calculate and write the power directly – event-driven, not only at the next poll cycle.

### Setup

1. In the integration's **options**, select the **grid feed-in entity** (a sensor in watts). Default sign convention: positive = surplus/feed-in, negative = grid consumption. If your sensor uses the opposite convention, enable **"Invert sign of the grid feed-in entity"**.
2. Enable automatic control via the new **"Auto control" switch entity**.

While "Auto control" is active, manual changes to the power number entity are **ignored** – instead, it continuously shows the value calculated by automatic control.

### Calculation

Whenever the grid feed-in entity changes, the following is calculated:

```
grid_feed_in_smoothed = min( moving_average(grid_feed_in_raw, smoothing_period), grid_feed_in_raw )
new_power             = current_power + grid_feed_in_smoothed − reserve
```

The sign inversion (if enabled) is applied **before** this calculation, so smoothing, minimum formation and the power formula all work consistently with the same sign convention.

- **Auto control smoothing** (number entity, default 5 s, `0` = disabled): period for a moving average over the raw grid feed-in values. So that short upward jumps (e.g. a passing gap in the clouds) do not immediately lead to unnecessary readjustment, the **minimum of average and current raw value** is used instead of the average directly – compared with signs, i.e. e.g. `-10` is smaller than `-5`, not by absolute value. A sudden **drop** in surplus (or a swing into grid consumption) therefore takes effect **immediately** despite smoothing, because in that case the (not yet adjusted) average would be higher than the current raw value and is therefore not used.
- **Reserve** (number entity "Auto control reserve", default 100 W): the surplus that should always remain untouched – a safety margin against grid consumption caused by measurement or control delays.
- **Auto control max. power**: hard upper limit for the calculated value (in addition to any power limit reported by the device).
- **Auto control rate limit** (default 1 s): minimum interval between two write operations, in case the grid feed-in entity updates very frequently. Smoothing continues independently with every sensor update, even if a single run does not lead to a write operation because of the rate limit.

This is a simple proportional controller with reserve/dead band: when surplus is above the reserve, power is increased; when surplus is below the reserve (or there is grid consumption), power is decreased – the control loop settles so that exactly the configured reserve of surplus flows into the grid.

### Interaction with the water heater and manual control

- **The "Auto control" switch is a standing setting, independent of the on/off state of the water heater.** If the water heater entity is "off" (whether explicitly switched off or automatically detected as "off", e.g. due to `no_control`/`device_disabled`), the function merely **pauses** – nothing is written to the ELWA any more. The switch itself stays on.
- If the water heater is then switched "on" again, **automatic control starts up by itself again**, as long as "Auto control" is still enabled – there is no need to operate the switch again.
- A `0 W` value calculated by automatic control does **not** switch the water heater off – "no surplus right now" is a normal, temporary state in which automatic control keeps running and waits for surplus to return.
- Your own automations that previously calculated and set the power should be disabled once "Auto control" is used, to avoid double control.

Register `1000` is explicitly exempt from my-PV's documented "write at most once a day" restriction, so the heartbeat or one-time writes described here are harmless.

## Register 1081 – device state

The official my-PV document lists register `1081` as `R/W` with the value range `0, 1`, without further description. From status code `21` "Device disabled (devmode = 0)", defined in the same document, it can be derived that register 1081 mirrors the device's `devmode` switch: **`0` = device disabled, `1` = device enabled.**

This integration exposes it as the **"Device enabled" switch entity**, with which the device itself can be switched on and off. This is a different concept from the on/off of the water heater entity: the latter only requests a power value via register `1000` while the device itself stays enabled; this switch disables the device completely, just as it would be possible via the device's web interface.

**Important regarding write frequency:** register `1081` is *not* among the registers explicitly approved for frequent writes (see the next section) – unlike the power register, it is therefore **never** rewritten automatically on every poll cycle, but only when the switch is explicitly toggled. Use this switch only for occasional, manual switching – do **not** include it in automations that would toggle it frequently (several times a day), so as not to unnecessarily wear the device's flash memory.

## Firmware version, hardware version, MAC address

The **firmware version** can be read via Modbus and is therefore shown both as a sensor and directly in the device info panel of the device entry:

- **Controller firmware**: composed of the main version (register `1016`) and the sub version (register `1028`), shown as `e<main>.<sub>` (e.g. `e4.18`). The official document only describes the raw format "u16 (exxxxxyy)" for both registers; the exact composition into a single version string is not conclusively specified – this rendering is a readable but not literally confirmed-by-my-PV interpretation.
- **Power stage firmware** (register `1017`, format `ep%03d`) and **co-controller firmware** (register `1086`, format `ec%03d`): these two formats are reliably confirmed, since they match exactly the values the device itself reports on its HTTP status page (`data.jsn`) as `psversion`/`coversion` (e.g. `ep001`, `ec005`).

**Hardware version and MAC address cannot be read via Modbus.** The official register table of the AC ELWA 2 does not define a hardware/board revision register. A MAC address is also missing – even the UDP discovery protocol described in the same document only returns IP address, serial number, firmware version and ELWA number in its reply, but no MAC address. Both could only be determined via the device's web interface (HTTP), which is outside the Modbus approach of this integration.

### Important note: write frequency of registers

According to the official my-PV documentation, **all writable registers may be written at most once a day** to avoid premature wear of the device's non-volatile memory – **except** registers `1000` (power), `1009`–`1012` (time/boost activate) and `1078`–`1080`. This particularly concerns:

- Register `1002` (target temperature, `Number` and `Water heater` entity of this integration): avoid automations that change this value several times a day.
- Register `1081` (device state, "Device enabled" `Switch` entity): only written on explicit switching, never automatically on every poll cycle – still do not use it in frequently running automations.
- Register `1014` (max. power) is deliberately only **read** by this integration, never written.

## Known limitations

- The integration has primarily been tested against the AC ELWA 2 with current firmware. Feedback on other firmware versions is welcome.
- Register 1081 is officially documented only with its value range, but without a textual meaning; the mapping 0 = disabled / 1 = enabled is a plausible derivation, but not literally confirmed by my-PV (see above).

## Why not the new HA Modbus backend (2026.9)?

Home Assistant 2026.9 introduced a new, config-flow based Modbus backend (library [`modbus-connection`](https://home-assistant-libs.github.io/modbus-connection/), now using [`tmodbus`](https://github.com/wlcrs/tmodbus) internally instead of `pymodbus`) – see the [release blog post](https://www.home-assistant.io/blog/2026/09/02/release-20269/#modernizing-modbus) and the [developer blog post "Modernizing Modbus"](https://developers.home-assistant.io/blog/2026/07/05/modernizing-modbus). It solves two problems:

1. Users set up devices via a UI config flow instead of manually maintaining register maps in YAML.
2. Several integrations that share a **physical bus** (e.g. an RS-485 bus or a TCP gateway with several devices from different manufacturers) get a shared connection ("unit") instead of blocking each other.

For this integration, this currently brings no added value:

- **Point 1 is already covered** – this integration has used a config flow from the start, not YAML register maps.
- **Point 2 does not apply in practice** – the AC ELWA 2 has its own IP address and its own Modbus TCP server. There is no other consumer with which a connection could be shared.
- The new backend is only about a month old at this point; `modbus-connection` and the suggested template pattern (standalone device library + vendored HACS integration) are a "let's get building" call, not an established pattern.
- A port would raise the minimum HA version significantly (currently `2026.5.0`) and require splitting into a standalone device library + integration – disproportionate for a small unofficial integration without the actual benefit (shared connections).

This integration therefore stays with `pymodbus` for now. The plan is to wait for a few more Home Assistant releases and to evaluate a switch to the new backend around the turn of the year 2026/2027 – provided the ecosystem has matured by then and there is a concrete benefit (e.g. a wish to be included in HA Core).

## Sources & acknowledgements

- **[my-PV: AC ELWA 2 – Documentation of Controls (PDF, version 241205)](https://download.my-pv.com/acelwa2/AC_ELWA_2_Documentation-Controls_EN241205.pdf)** – official, authoritative Modbus register table incl. status codes; basis of this integration's register mapping.
- [evcc-io/evcc – charger/mypv.go](https://github.com/evcc-io/evcc/blob/master/charger/mypv.go) – production-tested Modbus register control of the AC ELWA 2, used to cross-check the register data. No code was taken from this file; the file itself is, according to its header, not published under evcc's MIT license.
- [Modbuscloud – my-PV AC ELWA 2](https://www.modbuscloud.com/de/vorlagen/my-pv-ac-elwa-2-1821) – community register template, used for cross-checking.
- [my-PV/home-assistant-integration](https://github.com/my-PV/home-assistant-integration) – official integration, as a model for the covered feature set (sensors, target temperature).

This integration uses only register data (facts) from the sources above. The source code is written independently.

## License

MIT, see [LICENSE](LICENSE). This integration is an independent community project and is not affiliated with my-PV GmbH; "my-PV" and "AC ELWA" are trademarks of their respective owners.

## Logo and licenses

The logo in the `brand/` folder is based on the *water-boiler* icon from the [Material Design Icons](https://pictogrammers.com/library/mdi/) by Pictogrammers, licensed under the [Apache License 2.0](custom_components/mypv_elwa2_modbus/brand/LICENSE-MDI.txt). The lightning bolt and the colours were added or changed. The source code of this integration is licensed under the [MIT License](LICENSE).
