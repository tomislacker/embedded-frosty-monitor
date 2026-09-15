# Enclosure & Mounting Strategy

## Logger Core: IP65 Box Layout

The main enclosure houses the ESP32-S3-DevKitC-1, all breakouts, terminal blocks, and power inlet. Physical layout and sealing strategy:

### Internal Layout

| Zone | Component | Mounting | Clearance |
|------|-----------|----------|-----------|
| Lower tier | perfboard + standoffs (5–10mm height) | M3 nylon standoffs, countersunk | 15 mm clearance to enclosure floor |
| Lower tier | terminal blocks (field wiring screw terminals) | soldered to perfboard or DIN-rail clip | aligned with cable gland inlets on bottom/side |
| Middle tier | ESP32-S3 DevKitC-1 | dual-row header sockets to perfboard | GPIO header pins clear of other PCBs |
| Middle tier | ADS1115 + DS3231 + microSD breakouts | stacked via SMA or right-angle headers; alternative: breadboard frame | <5 mm stack clearance for airflow |
| Middle tier | MAX31855 + CT bias network | soldered onto veroboard fragment or separate small PCB | isolated from 5V power plane to reduce thermocouple reference noise |
| Upper tier | 5V/3A wall adapter or DC module (if internal PSU chosen) | mounted on side wall via adhesive strip or DIN-rail bracket | **do not block airflow; 5V is low power, minimal thermal load** |
| Top surface | 3 LEDs (recording, error, card) | panel-mount holders soldered to perfboard, grommet through enclosure face | LEDs protrude <5 mm into panel to minimize stress on solder joints during thermal cycling |

### Panel Mounting (Front Face)

**Included in IP65 enclosure front panel:**

- **2× momentary pushbuttons** (event-journal + spare): 12 mm stem, 40 mm spacing, waterproof IP67 caps
- **3× indicator LEDs** (5 mm, 20 mm row spacing): red (recording), amber (error), green (card status)
- **USB-C power bulkhead connector** (right-angle, stainless nut): mounted on lower-right panel for cable strain relief and dirt exclusion
- **Status label sticker** (optional): "Frosty Monitor v1 | Power: 5V DC | SD: microSD | I2C: internal pods"

### Cable Glands & Sealing

**Critical for IP65 integrity:**

| Entry Point | Gland Size | Cable Type | Sealed With |
|-------------|-----------|-----------|-------------|
| Bottom panel | PG7 (3.5–6 mm) | CT coil leads + CT bias network output | M20×1.5 PG7 elastomer gland |
| Bottom-left panel | PG9 (6–9 mm) | Shielded Cat5e to pod A (beater vibration) | M20×1.5 PG9 elastomer gland |
| Bottom-right panel | PG9 | Shielded Cat5e to pod B (compressor vibration) | M20×1.5 PG9 elastomer gland |
| Side panel, lower | PG7 | 1-Wire DS18B20 quad-chain pigtail | M20×1.5 PG7 elastomer gland |
| USB-C bulkhead | integral | 5V USB-C input only (no data lines) | stainless M16 compression nut + silicone washer |

**Cable gland discipline:**

1. Route all cables **perpendicular** to the enclosure wall (avoid sharp bends at gland entry).
2. Leave ~2 cm of un-stripped cable sheath inside the gland to avoid water creep along individual wire insulation.
3. Tighten gland nut hand-tight + 1/4 turn with a wrench; over-tightening deforms the cable sheath and voids the seal.
4. After deployment, inspect glands monthly for water beads or condensation inside the enclosure.

---

## DC-Only Rule

**Policy:** No AC power enters the logger enclosure. The 5V/3A USB-C adapter plugs into a **separate, dedicated 120VAC outlet**—never a shared circuit or power strip with machine controls.

**Rationale:**

- The 120VAC beater motor circuit and 24VAC contactor coil circuits carry transient noise (inrush spikes, relay chatter, motor brush noise).
- If AC mains wiring runs near logger power cables inside a shared strip, induced dI/dt noise couples into the 5V supply via parasitic inductance.
- The CT coil outputs and AC-presence opto modules are already isolated (magnetically and optically) to prevent noise coupling into the 3.3V logic rail.
- A separate outlet, far from machine circuits, is the final barrier against ground-loop noise and ensures clean 5V for the ADC reference.

---

## Logger Enclosure Placement

The IP65 box should be mounted **outside the machine cabinet** or in a **safe interior spot** away from:

- **Moving parts:** beater drive, compressor dome, condenser fan intake
- **Thermal stress:** condenser air discharge (80–90°C), evaporator frost buildup
- **Vibration:** compressor vibration isolation pad areas; use shock mounts if attached directly to the machine chassis
- **Grease/coolant spray:** from the beater drive lubrication and compressor shell condensation drip lines

**Recommended placement:**

- Velcro-strapped to the **exterior rear wall** of the cabinet, in a shaded area with passive airflow.
- Alternatively, mounted on a nearby **shelf or wall-mounted bracket** using M4 threaded inserts and stainless steel angles.
- Cable runs to pods routed through the cabinet frame or along existing wiring trays to minimize new penetrations.

**Thermal/ingress strategy:**

- Enclosure glands should face **downward or sideways** to shed rain/condensation; avoid top-facing openings.
- If deployed outdoors or in high-humidity environments (>85% RH), consider the optional **conformal coating spray** (bom.md add-on) on the main PCB as a vapor barrier.
- Ensure 50 mm clearance around the enclosure for passive convection; active cooling (fan) is unnecessary for 5V standby power draw (~2W idle).

---

## Sensor Pods: ADXL345 Vibration Modules

Each vibration pod houses a single ADXL345 breakout, potted/sealed in a mini-enclosure, and provides strain-relieved cable ingress.

### Pod Assembly

| Component | Material/Size | Purpose |
|-----------|---------------|---------|
| Mini-enclosure | ABS plastic, ~80×50×30 mm | weatherproof pod housing |
| ADXL345 breakout (GY-291) | PCB-mounted accelerometer, I2C output | 3-axis acceleration measurement |
| Potting compound | two-part epoxy or polyurethane | electrical insulation + moisture barrier |
| Strain-relief boot | silicone, 6 mm inner diameter | protects Cat5e pigtail from flexing |
| Cable pigtail | shielded Cat5e, 30–80 cm length, strain-relieved on both ends | I2C + power (GND + 3.3V + SDA + SCL) |
| JST-SM 4-pin connector | mating pair on pigtail and logger terminal block | <$1 detach point; allows pod swap without soldering |

### Mounting Strategy

**Pod A (beater drive vibration):**
- Adhesive-stud mounting (epoxy stud or permanent adhesive dot) on the painted steel beater-drive head cover.
- **Do NOT use magnets**—they decouple the accelerometer from the machine structure and attenuate true vibration.
- Pod orientation: accelerometer X-axis aligned with motor shaft rotation axis; Y/Z axes capture radial deflection.

**Pod B (compressor shell vibration):**
- Adhesive-stud mounting or epoxy stud on the unpainted compressor dome (high-temperature shell, 60–80°C during operation).
- Confirm adhesive thermal rating (>90°C) before deployment.
- **Alternative:** if adhesive fails, band-clamp with a rubber isolator strip to distribute stress and prevent micro-sliding.
- Pod orientation: Z-axis (often sensitive axis on ADXL345 breakouts) pointing toward the compressor cylinder centerline.

### I2C Wiring: Pod to Logger

Standard 4-wire configuration over shielded Cat5e:

| Wire | Color Pair | Signal | Logger Pin |
|------|-----------|--------|------------|
| 1 | orange / orange-white | 3.3V power | +3.3V rail |
| 2 | green / green-white | GND | GND rail |
| 3 | blue / blue-white | SDA (I2C data) | GPIO 8 + pull-ups |
| 4 | brown / brown-white | SCL (I2C clock) | GPIO 9 + pull-ups |
| Shield | bare copper braid | earth | connected to GND at logger end only (not pod end; prevents ground loop) |

Cable runs typically span 30–80 cm depending on machine layout. **If runs exceed 1 meter,** add P82B715 I2C buffer modules (bom.md optional add-ons section) or fallback to RS-485 bridge (not recommended initially).

---

## DS18B20 Temperature Probes

Four waterproof 1-Wire DS18B20 probes share a single signal line via star topology from the logger.

### Probe Placement & Dressing

| Probe | Location | Mounting | Thermal Contact |
|-------|----------|----------|-----------------|
| 1 | cylinder jacket (outer surface) | Kapton tape + zip ties | painted steel; wrap probe in 2 layers of kapton to reduce air-gap conduction |
| 2 | condenser air intake (plenum) | adhesive thermistor pocket | air stream, shaded from direct drip |
| 3 | condenser air discharge (outlet) | adhesive pocket downstream of coil | air stream; measure post-cooling temperature |
| 4 | ambient (control reference) | enclosure exterior, shaded side | passive air; avoid direct sun or radiant heat from the cabinet |

**Kapton tape dressing (probes 1–2):**
- Wrap probe tip in 1–2 layers of 50 µm kapton tape to minimize water/grease migration into the stainless-steel probe bulb.
- Secure kapton with small zip tie or electrical tape; avoid adhesive residue.
- Leave the connector and cable jacket exposed for easy service.

**1-Wire chain star topology:**

```
Logger GPIO 4 (with 4.7kΩ pull-up) ──┬── Probe 1 (cylinder)
                                      ├── Probe 2 (condenser air-in)
                                      ├── Probe 3 (condenser air-out)
                                      └── Probe 4 (ambient)
```

No daisy-chaining; each probe is a separate drop from a common 4-pin JST-SM connector or terminal block inside the logger enclosure. This topology avoids stub capacitance and simplifies probe ROM address mapping (see wiring-and-pinmap.md).

---

## K-Type Thermocouple: Compressor Discharge Line

A single K-type thermocouple probe monitors the compressor discharge (high-side) temperature for cycle efficiency and over-temperature detection.

### Mounting: Washer Compression Style

**Method:** Clamp the probe tip directly onto the discharge line copper tubing using a washer and compression nut (M8 or M10, depending on probe stem diameter).

**Steps:**

1. Clean the tubing with wire brush to remove oxidation; wipe with dry cloth.
2. Wrap the probe bulb in 1 layer of thin copper foil or aluminum foil to maximize contact conductivity.
3. Slide a stainless-steel 316 washer (OD > foil) over the probe stem.
4. Tighten the compression nut by hand + 1/4 turn with a wrench; **do not over-tighten** (can crack the probe ceramic insulator inside).
5. Verify the probe temperature reads 5–15°C above the piping surface (thermocouple IR thermometer spot-check during the first run).

### Wiring

The K-type thermocouple connects to the **MAX31855 amplifier module** (SPI, GPIO 14 CS). The MAX31855 provides:
- Cold-junction compensation (reference junction at 3.3V board temperature).
- Direct conversion to °C or °F.
- Fault detection (thermocouple break, short to ground/Vcc).

Probe leads are typically **red/yellow or red/blue (K-type standard)**. Polarity matters: **red lead = positive (Chromel)**, other lead = negative (Alumel). Reverse polarity gives inverted temperature.

---

## Leak-Sensing Add-Ons: Drop Counter, Moisture Pad, Gas Sensor

Leak sensing spans one base-config sensor (the drop counter) and two optional add-ons (moisture pad, gas sensor). All three mount as consumable-class pods on JST detach pigtails, the same discipline as the vibration pods and temperature probes above.

**Drop counter (base config):** Clips onto the drip tube outlet below the faceplate — the machine's factory-designed rear-seal telltale. **The tube must still drain freely; never plug or restrict it to fit the sensor.** The IR slot-type sensor straddles the drip path without narrowing it; after mounting, verify clear drainage, not just electrical function.

**Moisture pad (optional):** Placed under the drip tray / machine footprint to catch pooling the drop counter wouldn't see (spray, overflow, non-drip-tube leaks). Route the pigtail clear of foot traffic and any spot where a tech would step or roll equipment.

**Gas-sensor pod (optional, experimental):** Mounted low in the compressor compartment — refrigerant vapors are heavier than air — and positioned away from the direct condenser airflow blast, which would dilute or skew a reading before the sensor gets a representative sample.

All three use JST-SM detach pigtails, same as the vibration pods, so they can be unplugged for service or panel removal without disturbing the rest of the wiring.

---

## Contamination Strategy & Maintenance

### Sacrificial Parts Model

**The BOM divides hardware into two classes:**

1. **Reusable core** (logger enclosure, ESP32, breakouts): lives in a sealed box away from machine contact. Lifespan: 3–12 months per installation with normal maintenance.
2. **Consumable pods & probes** (ADXL345 modules, CT coils, DS18B20 probes, thermocouples): machine-contact, grease/sugar contamination inevitable. Lifespan: 2–6 months; then swap and replace.

**Contamination sources:**

- **Grease carryover:** beater-drive lubrication migrates via vibration and aerosol onto nearby surfaces, coating electronics and connectors within weeks.
- **Sugar residue:** incomplete rinse cycles leave syrup/sugar film on the compressor shell and condenser coils; hygroscopic film attracts moisture and becomes conductive.
- **Thermal cycling:** freeze–thaw stress on potted electronics and solder joints causes micro-fractures and creep failures.

### Service Workflow

**Every 3 months (or after high-contamination events like spillage):**

1. Visually inspect the logger enclosure for water beads or condensation inside; if present, drain via cable-gland inspection and allow 24 h air-dry.
2. Wipe down pod cables and connector bodies with isopropyl alcohol and dry cloth.
3. Inspect the ADXL345 potted pods for crazing or epoxy shrinkage; if observed, replace the pod within 2 weeks.
4. Confirm thermocouple probe contact on discharge line; retighten washer nut if loose.

**Every 6 months (end-of-season service):**

1. **Pod replacement:** Unplug JST-SM connectors and swap both ADXL345 pods if contamination is visible or opto modules fail thresholds.
   - Cost per pod: ~$15 (ADXL345 + mini-enclosure + pigtail + JST-SM connector).
   - Time: <5 min per pod with pre-assembled spares.
2. **Thermocouple swap:** If MAX31855 fault detection trips repeatedly or temperature readings are erratic, replace the probe (cost: ~$10; time: 10 min with spanner).
3. **DS18B20 probes:** If any probe stops responding on the 1-Wire chain, unplug the JST-SM drop and swap in a spare. Record new ROM address in the deployment manifest.
4. **CT coils:** If current measurements drift or clipping occurs, inspect the CT for visible contamination. If heavy grease/oil coating is present, swap the pair (cost: ~$12; time: 15 min).

### Optional Conformal Coating

If deployment is in extreme humidity (>90% RH for weeks) or high-contamination environment (fry oil, sugar dust):

- **Conformal coating spray can** (~$20, amortized across 2–3 builds): thin vapor-permeable polymer layer on the main PCB components (not connectors or buttons).
- Apply in a well-ventilated area; allow 24 h cure before enclosure closure.
- Coating does **not** replace potting of pod electronics; it is a supplementary moisture barrier for the main board only.
- Document coating batch and date for warranty/troubleshooting reference.

---

## Enclosure Checklist

- [ ] IP65 enclosure dimensions verified (200×150×75 mm fits logger + breakout stack + terminal blocks).
- [ ] Perfboard + standoffs (M3 nylon) sized to fit enclosure floor with 10 mm clearance to lid.
- [ ] LED panel-mount holders aligned and soldered; LED anode polarity verified (red/amber/green match intended function).
- [ ] Pushbutton stems secured with nylon nuts; momentary contacts confirmed with continuity tester.
- [ ] USB-C bulkhead connector soldered to 5V/GND rails; DC-only power confirmed (no AC adapter internal to enclosure).
- [ ] Cable glands (PG7/PG9) installed and tested for water ingress (spray test or submersion check at bench).
- [ ] All interior wiring strain-relieved and zip-tied; no sharp bends or abraded insulation.
- [ ] Enclosure mounting location identified: exterior, away from moving parts, condenser airflow, and thermal stress zones.
- [ ] Pod A assembly tested: ADXL345 responding on I2C (0x1D); adhesive cured and tested for creep.
- [ ] Pod B assembly tested: ADXL345 responding on I2C (0x53); adhesive rated for compressor dome temperature (>90°C).
- [ ] Thermocouple probe mounted on discharge line; contact verified with IR thermometer (±5°C accuracy).
- [ ] DS18B20 probes kapton-wrapped and mounted in final locations; 1-Wire chain ROM addresses recorded in manifest.
- [ ] All connectors labeled: pod A / pod B / sensor chain / CT bias network input.
- [ ] Spare pod kit (ADXL345 + mini-enclosure + pigtail) stored in a dry location; spare thermocouple in moisture barrier bag.

---

## Next Steps

After enclosure assembly and deployment:

1. Power on and run firmware initialization (scan I2C, confirm all four ADXL345 + DS3231 + ADS1115 addresses, test 1-Wire ROM enumeration).
2. Log deployment manifest JSON with probe/CT/thermocouple serial numbers and locations.
3. Record initial temperature/current/vibration readings over the first 24 h to establish baseline noise floor.
4. Confirm AC-presence opto modules fire correctly when beater/contactor/TCC/HP circuits energize (use firmware windowed edge counter for each GPIO).
5. Schedule first maintenance check at 3 months; document contamination observations and any pod/probe swaps.
