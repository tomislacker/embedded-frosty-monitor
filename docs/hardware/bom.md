# Bill of Materials — Frosty Monitor DAQ

## Configuration Philosophy

The base configuration targets **reusable logger core + consumable sensor pods** ($130–150 total). This split reflects the actual deployment lifecycle: the main enclosure lives outside the machine for months, while sensor pods contaminate with grease/sugar and require periodic replacement.

Budget generic sourcing (AliExpress/Amazon clones) keeps sacrificial parts within reach of frequent replacement; name-brand alternates (Adafruit) are noted per line for reliability-critical spots (RTC, MAX31855 thermocouple amp, ADS1115 ADC). Optional add-ons extend capability without inflating the base cost.

---

## Reusable Logger Core

| Item | Qty | Unit $ | Ext $ | Role | Notes |
|------|-----|--------|-------|------|-------|
| ESP32-S3-DevKitC-1 clone, N16R8 (16MB flash/8MB octal PSRAM) | 1 | 13.00 | 13.00 | main controller | Amazon/AliExpress; Adafruit #5336 N8R8 ($19.95) is the name-brand alternate |
| DS3231 RTC module with CR2032/CR1220 battery | 1 | 4.00 | 4.00 | timekeeping | Adafruit #3013 ($17.50) alternate |
| microSD SPI breakout | 1 | 2.50 | 2.50 | storage | Adafruit #254 ($7.50) alternate |
| ADS1115 16-bit 4-ch I2C ADC module | 1 | 4.00 | 4.00 | analog sensing | Adafruit #1085 ($14.95) alternate; **mandatory** for CT bias readings (see risks below) |
| MAX31855 K-type thermocouple amplifier module | 1 | 7.00 | 7.00 | thermocouple readout | Adafruit #269 ($14.95) alternate |
| Panel-mount LED, 5mm w/ holder | 3 | 0.70 | 2.10 | status indicators | recording / error / card status |
| 12mm momentary pushbutton, panel-mount | 2 | 2.50 | 5.00 | user input | event-journal + spare |
| UL-listed 5V/3A USB-C wall adapter | 1 | 10.00 | 10.00 | power inlet | plugs into separate outlet; DC-only enters enclosure |
| IP65 ABS enclosure ~200×150×75mm | 1 | 12.00 | 12.00 | main housing | |
| JST-SM connector kit (2/3/4-pin pairs) | 1 | 7.00 | 7.00 | pod detach points | one per pod pair |
| Terminal blocks, perfboard, standoffs, hookup wire | 1 | 8.00 | 8.00 | wiring infrastructure | |
| Cable glands PG7/PG9 assortment | 1 | 4.00 | 4.00 | sealed pass-throughs | sensor cable inlets |
| **Core Subtotal** | | | **$78.60** | | |

---

## Sacrificial / Consumable Sensor Pods

| Item | Qty | Unit $ | Ext $ | Role | Notes |
|------|-----|--------|-------|------|-------|
| SCT-013-020 split-core CT, 20A/1V built-in burden | 2 | 6.00 | 12.00 | current sensing | beater-motor leg + compressor leg; see risks below |
| CT bias network parts (resistors, 3.5mm jacks) | 1 | 2.00 | 2.00 | analog conditioning | |
| ADXL345 breakout (GY-291) | 2 | 4.00 | 8.00 | vibration sensing | beater drive + compressor shell; potted in pod enclosure |
| Shielded Cat5e patch cable, 1m | 2 | 4.00 | 8.00 | pod interconnect | 30–80cm active runs to logger; P82B715 I2C buffer recommended if runs exceed ~1 m (see wiring section) |
| DS18B20 waterproof probe | 4 | 3.50 | 14.00 | temperature chain | cylinder jacket, condenser air-in, condenser air-out, ambient |
| K-type thermocouple probe, ≥200°C, washer/compression style | 1 | 10.00 | 10.00 | discharge-line temp | see wiring section for mounting strategy |
| AC-presence optocoupler module (isolated, TTL out) | 2 | 2.50 | 5.00 | voltage sensing | 120V beater leg + 24V contactor coil; **bench-verify 24V threshold** (see risks below) |
| Pod mini-enclosure + mounting (epoxy stud/adhesive) | 2 | 3.00 | 6.00 | pod housing | sealed, potted electronics + strain-relieved cable |
| Misc: heat-shrink, epoxy, kapton tape, zip ties | 1 | 5.00 | 5.00 | assembly aids | cable dressing, conformal protection (optional) |
| **Consumable Subtotal** | | | **$70.00** | | |

---

## Base Configuration Total

| | |
|------|------|
| Core subtotal | $78.60 |
| Consumable subtotal | $70.00 |
| **Base Total** | **$148.60** |

**Status:** Target band $130–150 ✓ (lands at $148.60)

---

## Optional Add-Ons

Purchase these only if bench testing or deployment experience calls for additional instrumentation. Each line is independent:

| Add-On | Cost | Rationale |
|--------|------|-----------|
| 3rd SCT-013-020 CT | +$6.00 | whole-machine draw measurement (separate from beater + compressor legs) |
| TCC-microswitch + HP-switch opto taps (2 modules) | +$5.00 | state machine monitoring (if firmware expansion justifies real-time control logic) |
| Hopper DS18B20 probe | +$3.50 | product temperature tracking during fill cycles |
| P82B715 I2C buffer modules ×4 | +$12.00 | **install if pod cable runs exceed ~1 m or bench test shows glitches**; two per pod over shielded Cat5e |
| GX16 aviation bulkhead connector upgrade ×7 | +$17.50 | field-rugged pod/sensor detach (replaces JST-SM kit); sharper specs on mating cycles |
| Conformal coating spray can | +$20.00 | amortized across multiple builds; optional moisture/grease barrier for core board |
| Spare pod kit (ADXL345 + mini-enclosure + pigtail) | +$15.00 | swap contaminated pod in <5 min without field rework |
| RS-485 fallback parts: 2× Seeed XIAO RP2040 + 4× MAX485 module | +$16.80 | in-pod digital bridge if I2C pod cable runs prove fundamentally unreliable after bench test; not recommended unless P82B715 buffering fails |

---

## Why Sacrificial / Consumable?

Sensor pods—especially the ADXL345 breakouts and CT coils—mount directly on or inside operating machinery. Over 2–6 months of 24/7 runtime:

- **Grease & sugar contamination:** Condensed oil and product residue coat exposed electronics and connectors, raising leakage currents and eventual shorts.
- **Thermal stress:** Repeated freeze–thaw cycles on the compressor shell and condenser air streams degrade solder joints and potting compound.
- **Mechanical wear:** Vibration pods on the beater drive and compressor dome experience 10–100 g continuous acceleration; stress cracks in miniature capacitors and connection points are common.

**Mitigation strategy:** Design pods as under-$15 drop-in swaps. Use JST-SM (or GX16 for high-cycle sites) detach connectors and potted/sealed mini-enclosures so contamination does not spread to the core logger board. Kapton tape + zip ties dress thermocouples and DS18B20 probes to minimize grease ingress.

---

## Known Risks & Bench Verification

### (a) AC-Presence Opto Modules @ 24VAC — Threshold Mismatch

Many budget optocoupler breakouts ship sized for ~220VAC and specify trigger thresholds accordingly. A 24VAC contactor coil (especially a low-current logic-level gate) may not exceed the module's LED forward-drop threshold.

**Bench verification required:**  
Before first deployment, apply a bench DC power supply to simulate the 24VAC RMS voltage. Confirm the module's TTL output transitions cleanly. If not, the fallback is a **MOSFET-input isolation amp** (e.g., TI ISO7xx series, ~$5–8) or hand-rolled optocoupler with a lower threshold diode.

### (b) SCT-013-020 @ 20A Ceiling — Compressor Inrush

The SCT-013-020's nameplate 20A/1V ratio is tight against three-phase compressor locked-rotor inrush, which can spike to 2–3× FLA briefly at motor start. If the CT saturates, the voltage reading flattens and firmware loses current information during inrush.

**Bench verification:**  
Measure the CT output under real compressor start. If the scope shows clipping, swap the CT for **SCT-013-030 (30A/1V)**, a pin-compatible drop-in with a higher saturation point. Cost difference is negligible.

### (c) Never Wire CTs into ESP32-S3 Onboard ADC

The ESP32-S3's built-in ADC exhibits documented noise up to ~250 mV under load (from RF/WiFi cross-talk, PSU noise, and input coupling). For sub-1V CT bias measurements, this noise floor is unacceptable.

**Mandatory:** Use the external **ADS1115** (16-bit, I2C, inherently quieter front-end). It is non-negotiable.

### (d) No Affordable High-Fidelity Vibration Alternative

The ADXL345 is a mature, low-cost MEMS accelerometer. No affordable ADXL355 breakout (10× better noise floor) exists at <$20. If vibration resolution becomes critical, custom PCB or module integration is required—outside the scope of this no-PCB-fab constraint.

---

## Sourcing Notes

- **Core components** (ESP32, DS3231, ADS1115, MAX31855): AliExpress/Amazon generic clones are reliable; verify seller ratings and delivery time. Adafruit alternates carry QA overhead and 2–3× price but ship in 1–3 days to most US locations.
- **All prices are estimates**—verify at order time. Shipping, tax, and import delays vary by supplier and destination.
- **Pod consumables** (CTs, thermocouples, optocouplers) should be ordered in small batches to reduce stale inventory. Thermocouples and DS18B20 probes age slowly; CTs with potted coils can absorb moisture over years of storage.
- **Stock spares:** At minimum, keep one extra ADXL345 + mini-enclosure kit and one extra thermocouple probe on hand per installation.

---

## Machine-Readable BOM

See `../../hardware/bom.csv` for the canonical CSV mirror of this table. Use that file for automated inventory tracking and sourcing workflows.
