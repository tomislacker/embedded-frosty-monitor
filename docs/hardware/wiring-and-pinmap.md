# Wiring & Pin Map — ESP32-S3-DevKitC-1

## GPIO Assignments & Avoidance

### Pins to AVOID

Reserve these GPIO pins for internal functions. Using them will cause boot failures, system hangs, or silent malfunction:

| GPIO | Reason | Do Not Use For |
|------|--------|-----------------|
| 0, 3, 45, 46 | Strapping pins — read at boot to select SPI mode, download mode, etc. | any user function |
| 19, 20 | Native USB host/device PHY (DevKitC-1 has onboard ESP32-S3 USB bridge) | any user I/O |
| 26–32 | Flash SPI (QIO/DIO/QDI mode uses these for high-frequency bus) | any user I/O |
| 33–37 | Octal-PSRAM reserved (8MB PSRAM variant uses the full range; 8MB PSRAM is this build's configuration) | any user I/O |
| 43, 44 | UART0 console/CLI (TX/RX via USB bridge) | any user I/O; firmware printf() uses this path |

---

## Master Pin Assignment Table

| GPIO | Function | Bus | Direction | I2C Address | Notes |
|------|----------|-----|-----------|-------------|-------|
| 1 | LED 1: recording | — | output | — | sink to ground via ~1 kΩ current-limit resistor; active-high |
| 2 | LED 2: error | — | output | — | sink to ground via ~1 kΩ resistor; active-high |
| 4 | 1-Wire DS18B20 chain | 1-Wire | bidirectional | — | external 4.7 kΩ pull-up to 3.3V (see pull-up note below); all four DS18B20 probes share this line |
| 5 | LED 3: card status | — | output | — | sink to ground via ~1 kΩ resistor; active-high |
| 6 | Button 1: event-journal | — | input | — | internal pull-up enabled; active-low (push grounds pin) |
| 7 | Button 2: spare/mode | — | input | — | internal pull-up enabled; active-low |
| 8 | I2C SDA | I2C (shared) | open-drain | 0x48, 0x68, 0x1D, 0x53 | four devices on one bus (see pull-up note); pod buffering via P82B715 if cable >1 m |
| 9 | I2C SCL | I2C (shared) | open-drain | — | same bus as GPIO8; see pull-up note |
| 10 | SPI CS: microSD | SPI (shared) | output | — | active-low chip select |
| 11 | SPI MOSI | SPI (shared) | output | — | shared bus: microSD + MAX31855 (MAX31855 is read-only, not driven on MOSI) |
| 12 | SPI SCK | SPI (shared) | output | — | 10–20 MHz clock; all SPI slaves listen |
| 13 | SPI MISO | SPI (shared) | input | — | input from microSD + MAX31855 |
| 14 | SPI CS: MAX31855 | SPI (shared) | output | — | active-low chip select; thermocouple data read-only |
| 15 | AC-presence 1: 120V beater leg | digital | input | — | opto module TTL output; pulls to 3.3V when AC live; inverted (opto sink = no AC) |
| 16 | AC-presence 2: 24V contactor coil | digital | input | — | opto module TTL output; **bench-verify threshold before deployment** (see bom.md risks) |
| 17 | AC-presence 3: TCC microswitch node | digital | input | — | optional; opto module TTL output; pulls to 3.3V when energized |
| 18 | AC-presence 4: HP switch node | digital | input | — | optional; opto module TTL output; pulls to 3.3V when energized |
| 21 | DRIP_PULSE: drip tube drop counter | digital | input | — | IR slot-type optical drop counter clipped at the drip tube outlet (rear-seal telltale below the faceplate); debounced pulse counting in firmware; **base config** — see bom.md leak-sensing notes |
| 38, 39, 40, 41, 42, 47 | Spare | — | — | — | available for future expansion |
| 48 | RGB LED (onboard DevKitC-1) | SPI | output | — | WS2812B protocol; can be repurposed if RGB status not needed |

---

## I2C Bus: Shared @ GPIO 8 (SDA) & GPIO 9 (SCL)

### Devices & Addresses

| Module | I2C Address | Function | Role |
|--------|-------------|----------|------|
| ADS1115 (16-bit ADC) | 0x48 | CT bias voltage + optional leak-sensing analog channels | **mandatory**; see bom.md risk (c) |
| DS3231 (RTC) | 0x68 | system clock + NVRAM (EEPROM optional at 0x57) | low-power timekeeping across SD card writes |
| ADXL345 pod A (beater drive vibration) | 0x1D | ALT ADDRESS pin tied HIGH | breakout onboard pull-up + this GPIO config |
| ADXL345 pod B (compressor shell vibration) | 0x53 | ALT ADDRESS pin LOW/grounded | breakout onboard pull-up + this GPIO config |

### ADS1115 Analog Channel Map

| Channel | Signal | Notes |
|---------|--------|-------|
| A0 | CT-1: beater-motor leg (biased/filtered) | see CT Bias Network below |
| A1 | CT-2: compressor leg (biased/filtered) | see CT Bias Network below |
| A2 | Moisture pad (**optional add-on**) | capacitive soil-moisture-style pad; under-machine/drip-tray pooling detection; see bom.md optional add-ons |
| A3 | Refrigerant gas sensor (**optional, experimental add-on**) | semiconductor gas-sensor module, mounted low in the compressor compartment; heater powered from the 5V rail; **bench-validate before trusting readings** — see bom.md risk (e) |

### Pull-Up Resistor Note

Most breakouts ship with onboard 4.7 kΩ pull-ups on SDA/SCL. With four devices stacked, the cumulative pull-up conductance (~1.2 mS at 3.3V) creates a steeper rise time and shifts the logic threshold downward. Symptoms: CRC errors, occasional NACKs, or intermittent timeouts.

**Recommended action (bench-test first):**

1. Measure SDA/SCL rise time with a scope in normal operation (no pods plugged in).
2. If rise time is >1 µs at 100 kHz bus speed, inspect all four breakouts and **clip or desolder pull-ups from three of them**, keeping one set intact. Mark the kept set to avoid confusion in future replacements.
3. If rise time is <500 ns and bus errors do not occur, no action needed.

### Pod I2C Buffering via P82B715

If **cable runs exceed ~1 meter** (e.g., sensor pod is >1 m from logger box), I2C signal integrity degrades due to capacitive loading and line reflections. The **P82B715** is a push-pull I2C buffer that regenerates sharp edges and isolates capacitive load.

**Fallback buffering strategy (only if bench test shows glitches):**

- Install a P82B715 module pair on each pod side of the Cat5e run (one at logger, one at pod).
- Connect 4× P82B715 buffers: 2 per pod (beater + compressor).
- The buffer isolates the on-pod ADXL345 from logger I2C, allowing longer cable runs without retries or corruption.
- Pair cost: ~$3 per pod (P82B715 module ~$3, no extra connectors needed).

**Alternative fallback (RS-485 bridge, not recommended initially):**

If P82B715 buffering still fails after bench verification:

- Deploy a **Seeed XIAO RP2040** ($5.40) + **MAX485 RS-485 transceiver** ($1.50) module **on each pod** to convert I2C→RS-485 over the Cat5e cable.
- Logger side: another XIAO RP2040 + MAX485, programmed as RS-485→I2C bridge.
- Cost: ~$8.40 per pod pair (2× XIAO + 4× MAX485); effective only if hardware reliability demands justify firmware complexity.
- **Deferred to optional add-ons** section in bom.md; only implement if documented field failures occur.

---

## SPI Bus: GPIO 11 (MOSI), GPIO 12 (SCK), GPIO 13 (MISO)

### Chip Selects

| Module | CS GPIO | Frequency | Notes |
|--------|---------|-----------|-------|
| microSD card | 10 | 20 MHz typical | full-speed reads/writes; shared MOSI/MISO/SCK with MAX31855 |
| MAX31855 thermocouple amp | 14 | 2–5 MHz typical | read-only (no MOSI data); continuous conversion mode software-polled |

**Sharing MOSI/MISO/SCK:** Both devices listen to clock and MISO/MOSI lines; only the asserted CS (GPIO 10 or 14 going low) determines which device responds. Firmware must respect CS assertion order to avoid bus conflicts. No special consideration needed; standard SPI protocol.

---

## 1-Wire Bus: GPIO 4

### DS18B20 Temperature Chain

All four DS18B20 probes (cylinder jacket, condenser air-in, condenser air-out, ambient) share a single 1-Wire bus on GPIO 4 with an external **4.7 kΩ pull-up to 3.3V**. The pull-up must be placed **at the logger board**, not distributed to each probe.

### ROM Address → Location Mapping

Each DS18B20 carries a factory-burned 64-bit ROM address (e.g., `28:FF:AB:CD:EF:00:12:34`). Record the mapping in your **deployment manifest** (a JSON file in the SD card root, e.g., `manifest.json`):

```json
{
  "deployment_id": "frosty_factory_01",
  "start_date": "2025-02-14",
  "ds18b20_map": {
    "28:FF:AB:CD:EF:00:12:34": "cylinder_jacket",
    "28:FF:A1:B2:C3:D4:E5:F6": "condenser_air_in",
    "28:FF:12:34:56:78:9A:BC": "condenser_air_out",
    "28:FF:FE:DC:BA:98:76:54": "ambient"
  },
  "ct_map": { ... },
  "thermocouple_sn": "TC-202501-001"
}
```

Firmware reads ROM addresses at startup and logs them; use this manifest to label recorded data columns post-facto if probes are physically swapped during installation.

---

## Digital Inputs: AC-Presence Opto Modules

GPIO 15, 16, 17, 18 connect to TTL outputs from isolated optocoupler modules. **Important behavior:**

When an AC (or DC contactor) voltage is applied to the opto input:
- The LED inside the module lights, transistor conduct, and TTL output **sinks to ground** (low).
- Firmware reads this as a high-frequency pulse train at **50/60 Hz** (AC line frequency or rectified DC).

**Firmware does not read opto outputs as simple digital levels.** Instead:

1. Use **windowed activity detection**: sample the GPIO for ~100 ms and count low-going edges.
2. If edge count > threshold (e.g., >3 edges in 100 ms), declare the input "active."
3. This rejects noise spikes and contact bounce while tolerating the pulse train.

For DC inputs (24V contactor coil, TCC microswitch logic signal):
- If the DC voltage is steady, the opto LED stays lit, transistor conducts, and the output is a **continuous low pulse train** (50–60 Hz ripple from the internal opto photodiode response).
- The same windowed edge-count logic works: steady DC ⇒ continuous pulses ⇒ edge count saturates.

See firmware `src/pins.h` and application code in `src/ac_sense.c` (or equivalent) for the sampling loop.

---

## Power Distribution

### 5V Supply

- **USB-C wall adapter (5V/3A)** plugs into a separate wall outlet, **never shared** with machine control circuits.
- USB-C bulkhead connector on logger enclosure passes 5V in, GND return to adapter.
- The onboard **AMS1117-3.3 regulator** on the ESP32-S3-DevKitC-1 steps 5V down to 3.3V for the SoC and I/O rails.

### 3.3V Rail

All peripheral modules run at 3.3V:

| Module | Voltage | Notes |
|--------|---------|-------|
| ESP32-S3 SoC | 3.3V | main controller; onboard regulator sourced from USB 5V |
| ADS1115 ADC | 3.3V | I2C, ADC inputs up to 3.3V (single-supply mode) |
| DS3231 RTC | 3.3V | I2C; CR2032/CR1220 battery (3V nominal) handles timekeeping during power loss |
| ADXL345 breakouts | 3.3V | I2C, 3-axis acceleration ±16 g range |
| MAX31855 | 3.3V | SPI, thermocouple reference junction at 3.3V digital I/O, external thermocouple only |
| microSD card | 3.3V | SPI; most modern microSD cards tolerate 3.3V (older cards may require 3.0V regulator; test before deployment) |
| AC-presence opto modules | 3.3V | TTL outputs into GPIO inputs; LED+photodiode pairs run at 3.3V logic power |

### CT Bias Network

The two SCT-013-020 current transformers output ~1V AC at full scale (20A). A **bias network** (voltage divider + filter) centers this 1V AC signal at 3.3V/2 (1.65V midpoint) and low-pass filters the signal before the ADS1115 samples it.

- **Bias resistor pair:** 10 kΩ (3.3V to bias node) + 10 kΩ (bias node to GND); 3.3V/2 appears at the junction.
- **AC input:** CT secondary into a ~100 kΩ resistor, then 100 nF capacitor to the bias node. The RC time constant (~10 ms) smooths high-frequency noise.
- **Output:** biased, filtered signal into ADS1115 channel input (0.0–3.3V range, 1.65V ± ~0.5V during operation).

Firmware reads the ADC and computes RMS current: `I_rms = (ADC_reading_AC / 3.3V_max) * 20A * 0.707`.

---

## Wiring Checklist

- [ ] ESP32-S3-DevKitC-1 mounted on perfboard with standoffs; 5V/GND power rails soldered to USB-C bulkhead inlet.
- [ ] I2C pull-ups inspected and reduced to one set of 4.7 kΩ resistors (see pull-up note above).
- [ ] All I2C devices (ADS1115, DS3231, ADXL345 modules) soldered or breadboard-mounted and verified with `i2cdetect`.
- [ ] SPI microSD + MAX31855 CS pins wired to GPIO 10 and 14 respectively; MOSI/MISO/SCK routed to GPIO 11/13/12.
- [ ] 1-Wire DS18B20 pull-up resistor (4.7 kΩ, 3.3V to GPIO 4) mounted at the logger board.
- [ ] Button pins (GPIO 6, 7) pulled high via internal pull-ups; momentary switches connect to GND.
- [ ] LED pins (GPIO 1, 2, 5) each have a 1 kΩ current-limit resistor in series to ground; active-high sourcing from GPIO.
- [ ] AC-presence opto modules wired: AC/DC input from machine, 3.3V/GND power, TTL output to GPIO 15/16/17/18.
- [ ] CT coils wired to bias network; output into ADS1115 channels A0/A1.
- [ ] Drop counter (base config) wired to GPIO 21 (DRIP_PULSE); optional moisture pad wired to ADS1115 channel A2 and/or gas sensor to channel A3 if installed (see bom.md risk (e) before trusting gas-sensor readings).
- [ ] Shielded Cat5e cables connect sensor pods to logger enclosure, terminated with JST-SM connectors.
- [ ] Pod ADXL345 modules ALT ADDRESS pins strapped correctly: pod A (beater) HIGH (0x1D), pod B (compressor) LOW (0x53).
- [ ] All logic-level signals isolated from AC 120V beater leg and 24V contactor coil via optocouplers (not direct GPIO).

---

## Firmware Sync

**Critical:** The following firmware files must stay in sync with this table:

- **`src/pins.h`:** C header defining GPIO constants (e.g., `#define LED_RECORDING 1`).
- **`hardware/pinmap.csv`:** machine-readable mirror of this table.

After any pin reassignment, update all three sources before rebuilding firmware. Out-of-sync definitions silently wire inputs to wrong physical pins, causing data corruption or unsafe operation.

---

## Machine-Readable Pin Map

See `../../hardware/pinmap.csv` for the canonical CSV mirror of the master assignment table above.
