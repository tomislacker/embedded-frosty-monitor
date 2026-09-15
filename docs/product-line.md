# Product line: one platform, four tiers

frosty-monitor is one platform — the same on-card data format, the same
offline analysis stack, the same firmware HAL and `IStorageSink` transport
abstraction (per
[ADR 0002](adr/0002-microsd-storage-with-transport-abstraction.md)) — built
out across four hardware tiers that trade sensing density, storage, and
transport for cost. See
[ADR 0007](adr/0007-product-tier-strategy.md) for the decision record behind
this structure.

This is the internal product-line reference. For customer-facing pricing
built on these tiers, see
[proposal/service-proposal.html](../proposal/service-proposal.html).

## Tier comparison

| Tier | Name | BOM (est.) | Sensing channels | Storage / transport | Install | What it catches | Status |
|---|---|---|---|---|---|---|---|
| 1 | **Guard** | ≈$26 | 1× CT (compressor), 2× DS18B20 temp, IR drip counter | Internal flash rolling log; BLE walk-up readout at service visits | Permanent, every machine | Short-cycling, no-cold, seal drip, coarse condenser health | Designed |
| 2 | **Logger** | ≈$55–70 | Guard + 2nd CT (beater), 1× ADXL345 vibration pod | microSD or BLE offload; RTC-timestamped | Permanent | Guard + vibration signatures (belt/bearing), richer trend history | Designed |
| 3 | **DAQ Pro** | $152.60 | Full 17-channel kit — see [docs/hardware/bom.md](hardware/bom.md) | microSD (`SdSink`) | Portable, temporary | Full diagnostic depth: all known failure signatures | **Built** — M0 firmware + docs complete; bench bring-up next |
| 4 | **Live** | $160 (WiFi) / ≈$210 (cellular) | DAQ Pro-class sensing + connectivity | Cloud (`CloudSink`) — AWS IoT Core, 1-min aggregates; local buffering on link loss | Permanent + connectivity | DAQ Pro + real-time remote visibility, SMS/email alerts within seconds | Firmware `CloudSink` + AWS Terraform skeleton **in progress** this iteration; pilot after DAQ Pro bench validation |

DAQ Pro is the flagship built today and the rest of this repo's firmware,
hardware, and install-guide docs are written from its point of view. Guard,
Logger, and Live are the same platform pointed at different budgets and
deployment models, not separate products — see
[Platform leverage](#platform-leverage-one-firmware-stack-four-tiers) below.

## Per-tier BOMs

All prices below are estimates from component research, not verified
purchase orders — see [Sourcing notes](hardware/bom.md#sourcing-notes) in
the DAQ Pro BOM for the same caveat applied there. Single-unit vs
bulk/volume pricing is called out per line where it materially changes the
tier total.

### Tier 1 — Guard

| Item | Est. cost | Notes |
|---|---|---|
| ESP32-C3 Super Mini | $3.68 single / $2.22 bulk | WiFi4 + BLE5 confirmed on this module; same HAL as the S3, subset build — see [Platform leverage](#platform-leverage-one-firmware-stack-four-tiers) |
| 1× SCT-013-020 CT (compressor leg) + bias network | ≈$8 | clamp-on, not shunt-based — see [CT vs. shunt](#why-a-clamp-on-ct-not-a-cheaper-shunt-board) |
| 2× DS18B20 (cylinder jacket, condenser out) | ≈$6 | |
| IR drop counter (drip tube) | ≈$1.50 | same sensor as DAQ Pro's leak-sensing base config |
| Status LED + ack button | ≈$1 | local alert only, no display |
| IP65 enclosure, ~100×70×40mm | ≈$1.50 | much smaller than DAQ Pro's ~200×150×75mm core enclosure — no pod bays, no card slot |
| 5V PSU module + wiring/misc | ≈$5 | |
| **Total** | **≈$26** | bulk MCU pricing; ≈$27.7 at single-unit MCU pricing |

No SD card: history lives in a rolling log in internal flash, read out over
BLE when a tech is on-site. Local LED alert covers short-cycling, no-cold,
and drip conditions without a network or a phone in the loop.

### Tier 2 — Logger

Guard's BOM plus:

| Item | Est. cost | Notes |
|---|---|---|
| microSD SPI breakout | ≈$2.50 | same part as DAQ Pro's |
| DS3231 RTC module | ≈$4 | same part as DAQ Pro's; Guard has no RTC, Logger needs one for trend timestamps independent of BLE sync |
| 1× ADXL345 vibration pod w/ cable | ≈$8 | one pod (vs. DAQ Pro's two) — beater or compressor, whichever the deployment prioritizes |
| 2nd CT (beater leg) + bias | ≈$6 | |
| Larger enclosure (fits SD + RTC + extra wiring) | delta ≈$3–5 over Guard's | |
| **Total** | **≈$55–70** | range reflects single- vs bulk-unit sourcing and enclosure-size choice |

SD-or-BLE offload and quarterly trend reports. This is the tier where
vibration-based signatures (belt slip, bearing wear) become available on a
permanent install, not just during a portable DAQ Pro deployment.

### Tier 3 — DAQ Pro

Full BOM lives in [docs/hardware/bom.md](hardware/bom.md) — $152.60,
reusable logger core ($78.60) + consumable sensor pods ($74.00). Not
duplicated here; that document is the canonical source.

### Tier 4 — Live

DAQ Pro-class sensing plus connectivity. The ESP32-S3 already has WiFi
on-board, so the WiFi variant is close to a firmware-and-enclosure change,
not a new sensing BOM:

| Item | Est. cost | Notes |
|---|---|---|
| DAQ Pro base | $152.60 | unchanged sensing kit |
| Certs/provisioning (per-device X.509, production flow) | ≈$3–5 | one-time per-unit cost, not recurring |
| Antenna-conscious enclosure delta | ≈$4–5 | keep the WiFi antenna clear of the metal chassis DAQ Pro's stock enclosure doesn't have to worry about |
| **WiFi Live total** | **≈$160** | |
| + Blues Notecard (cellular option) | ≈$49 | 10-yr / 500MB prepaid data bundled — see [connectivity economics](#connectivity-economics) |
| **Cellular Live total** | **≈$210** | for venues without usable WiFi |

## Platform leverage: one firmware stack, four tiers

Every tier ships the same on-card/on-wire data format, the same
`IStorageSink` abstraction (per
[ADR 0002](adr/0002-microsd-storage-with-transport-abstraction.md)), and the
same offline analysis stack downstream — the signature detectors in
[docs/roadmap.md](roadmap.md) run against the same channel definitions
regardless of which tier produced them. What changes per tier is which
sinks and which subset of sensing channels are compiled in:

- **DAQ Pro** ships `SdSink` today.
- **Live** adds `CloudSink` on top of the same S3 hardware — see
  [docs/firmware/connectivity.md](firmware/connectivity.md) for the
  firmware side and [docs/cloud/architecture.md](cloud/architecture.md) for
  the AWS side.
- **Guard/Logger** are a firmware HAL *subset* build on the ESP32-C3 — same
  driver interfaces, fewer channels compiled in, a rolling-flash or
  `BleSink` target instead of `SdSink`/`CloudSink`. This is a roadmap item,
  not yet ported; see [docs/roadmap.md](roadmap.md).

This is the reason a four-tier product line doesn't mean four firmware
codebases or four analysis pipelines: it means one HAL, one data format, one
detector suite, and a per-tier compile-time selection of channels and sink.

## Why a clamp-on CT, not a cheaper shunt board

Guard's compressor-leg current sensing uses a split-core SCT-013-020 CT
(≈$8 with bias network), not a cheaper shunt-based HLW8012-class energy
monitoring board (roughly $2–3 less per unit). This is deliberate: a shunt
wires in series with the load, which means cutting into the compressor
leg's conductor and landing exposed line-voltage connections inside the
install. That's an installer burden and a safety step we refuse to impose
at the every-machine, permanent-install tier — a clamp-on CT goes around an
existing insulated conductor with no cut, no exposed terminal, and no extra
lockout/tagout step beyond what the install already requires. The same
reasoning already governs DAQ Pro's CT choice (see
[docs/hardware/bom.md](hardware/bom.md), risk (b)); Guard just makes the
same call under tighter cost pressure instead of loosening it.

## Connectivity economics

### AWS cost summary

Live's cloud path (AWS IoT Core → Kinesis Firehose → S3/Athena) lands at
roughly **$0.11/device/month** at one aggregated message per minute,
including 10 SMS alerts/month. Rough breakdown at that message rate
(43,200 messages/month, small payloads):

| Component | Est. monthly cost/device |
|---|---|
| IoT Core connectivity (persistent MQTT, ~43,200 device-minutes) | ≈$0.003 |
| IoT Core messaging (43,200 messages) | ≈$0.04 |
| S3 storage + Firehose (small aggregated payloads) | negligible |
| SNS SMS alerts (10/month, US) | ≈$0.065 |
| **Total** | **≈$0.11** |

AWS's free tier covers most of this for the first year on a small pilot
fleet. Dashboards (Grafana Cloud or ThingsBoard free tiers) are free at
pilot scale and are a separate cost line if a fleet grows past free-tier
limits. This is a summary; the authoritative build lives in
[docs/cloud/architecture.md](cloud/architecture.md).

### Cellular options

For venues without usable WiFi, Live's cellular add-on has three realistic
paths:

| Option | Upfront | Data plan | Integration effort | Notes |
|---|---|---|---|---|
| **Blues Notecard** | ≈$49 | 10-yr / 500MB prepaid, bundled (Blues Connectivity Assurance tops up automatically) | Low — Notecard handles the cellular stack and relays to Notehub over I2C; firmware talks to one well-documented module | Highest upfront cost, lowest ongoing account-management burden; single-vendor dependency |
| **SIM7080G + 1NCE** | ≈$45 module + $13 lifetime SIM | 1NCE's flat 10-yr/500MB lifetime SIM, ≈$58 all-in | Higher — own AT-command modem driver, own MQTT/cert handling in firmware | Cheapest all-in prepaid option; more firmware work, no bundled cloud relay |
| **Hologram** | ≈$3 SIM + $1/mo/SIM | Pay-as-you-go, ≈$0.03/MB (or discounted fleet plans) | Pairs with the same SIM7080G-class hardware as the 1NCE path | Best fit for uncertain/variable data volume; at Live's ~8.6MB/month aggregate traffic this runs ≈$1.26/month (≈$15/yr) ongoing — cheaper than the prepaid options over a short pilot, but it's a recurring bill instead of a one-time prepay, which cuts against the buy-once economics that make Guard/Logger's calculus work at every-machine volume |

Recommendation: Notecard for the pilot (lowest integration risk while
validating that Live's cloud path earns its keep at all); revisit
SIM7080G+1NCE or Hologram once cellular Live volume justifies the extra
firmware investment.

## Build-out sequence

1. **Validate DAQ Pro at bench, then in the field.** This is the deepest
   sensing tier and the only one already built; every other tier's alert
   thresholds and failure-signature calibration are derived from DAQ Pro
   data, not invented independently.
2. **Live pilot, one friendly customer.** Reuses DAQ Pro's sensing BOM
   almost unchanged; the new surface area is `CloudSink` and the AWS stack,
   which is lower risk to validate on a single site than a fleet.
3. **Logger.** A cost-reduced, permanent-install subset once Live's pilot
   has proven the cloud path is worth building toward, and DAQ Pro/Live
   field data has validated which channels matter enough to keep at a
   lower tier.
4. **Guard at volume.** The cheapest tier, meant to go on every machine —
   built last because its coarse thresholds (duty-cycle short-cycling, drip
   rate, no-cold) need to be validated against real DAQ Pro/Logger data
   first, and because it's the tier where an ESP32-C3 firmware port has to
   exist before anything ships.

Rationale in one line: **each tier's thresholds and calibration come from
the tier above it**, so building top-down (DAQ Pro → Live → Logger → Guard)
means every tier ships with field-validated thresholds instead of guesses.

## Risks

- **C3 ADC quality for CT sensing at Guard tier.** The ESP32-C3's onboard
  ADC is noisier than the external ADS1115 DAQ Pro/Logger rely on (see
  [docs/hardware/bom.md](hardware/bom.md), risk (c)), and Guard's BOM has no
  budget for an external ADC. Expect coarse duty-cycle short-cycling
  detection only, not the resolved current waveform DAQ Pro captures —
  bench-validate before claiming more.
- **ESP32-C3 single-core timing for BLE + sampling.** Unlike the S3's dual
  core, the C3 is single-core; running BLE walk-up readout concurrently
  with sensor sampling on one core needs bench validation that neither
  starves the other, especially during a BLE connection event.
- **Flash-wear for SD-less logging.** Guard's rolling log lives in internal
  flash with no SD card to absorb write cycles. Wear-leveling and log
  rotation need to be sized against the flash's rated write-cycle budget
  before this ships to a permanent, unattended install.
- **Cheap-module supply variability.** Guard and Logger lean on
  budget-sourced modules (ESP32-C3 Super Mini clones, generic CT coils) at
  a much thinner margin than DAQ Pro's already-budget-conscious BOM;
  batch-to-batch variation in cheap suppliers is a real risk at
  every-machine volume in a way it isn't for a handful of portable DAQ Pro
  units. Verify seller ratings and consider a second source before scaling
  orders.
