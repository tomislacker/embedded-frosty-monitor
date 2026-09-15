# embedded-frosty-monitor

A portable diagnostic data logger for Frosty Factory 117A/127A/137A frozen-drink
machines. A service tech temporarily installs it inside a machine, lets it run
for days to weeks logging vibration, current draw, temperatures, and
control-state, then pulls the SD card and analyzes the data offline to find
the root cause of an intermittent or hard-to-diagnose fault.

This is not a permanently-installed product. It is a bench/field diagnostic
tool: one unit, moved from machine to machine, that turns "it acts up
sometimes" into a timestamped record of what the compressor, beater motor,
and control chain were actually doing.

## Who this is for

- **Service technicians** who need to capture what a machine does between
  visits, correlate an intermittent symptom (short-cycling, failure to
  freeze, knocking, belt slip) against a timestamp, and bring evidence back
  to the bench instead of a guess.
- **The project owner**, building and maintaining the hardware, firmware, and
  analysis pipeline, and using field data to refine failure-signature
  detection over time.

## What it does

- Logs two AC current channels (beater motor leg, compressor leg) via CT
  clamps, sampled at 1 Hz with transient-burst capture on spikes.
- Logs vibration at the beater drive and the compressor shell via
  accelerometer pods, both as running RMS/peak/band-energy summaries and as
  raw windowed bursts (periodic and trigger-on-event).
- Logs four to five temperatures (cylinder jacket, condenser air in/out,
  ambient, optional hopper) plus compressor discharge line temperature via
  thermocouple.
- Logs digital AC-presence state on the beater leg and the 24VAC contactor
  coil, so control-chain behavior (is the compressor actually trying to run)
  is visible alongside the analog channels.
- Timestamps everything against a battery-backed RTC, independent of network
  time.
- Writes a self-describing record set to a microSD card: a manifest, daily
  CSV channel logs, binary vibration bursts, a vibration summary CSV, and a
  JSONL event log — no proprietary format, no required companion service.
- Lets the tech mark a moment as notable with a physical event button,
  producing a first-class timestamped incident marker independent of any
  later annotation.
- Splits into a reusable "logger core" (the electronics, in an IP65
  enclosure) and cheap, detachable "sensor pods" that take the grease/sugar
  contamination and get replaced, not the core.

## Repo map

| Path | Owner content | Description |
|---|---|---|
| [`docs/`](docs/) | this doc set | Architecture, ADRs, safety, roadmap, install guides |
| [`docs/architecture/`](docs/architecture/overview.md) | this doc set | System overview and data-flow diagrams |
| [`docs/adr/`](docs/adr/template.md) | this doc set | Architecture decision records |
| [`docs/hardware/`](docs/hardware/) | hardware docs | Wiring, enclosure, sensor placement, BOM |
| [`docs/firmware/`](docs/firmware/architecture.md) | firmware docs | Firmware architecture and on-card data format spec |
| [`docs/install-guides/`](docs/install-guides/137A.md) | install-guide docs | Per-model install procedures (117A/127A/137A) |
| `firmware/` | firmware team | PlatformIO project: FreeRTOS tasks, drivers, storage sinks |
| `hardware/` | hardware team | Schematics, enclosure files, BOM source |
| `analysis/` | analysis team | Offline Python analysis pipeline and tests |

## Quickstart

### Firmware

```
cd firmware
pio run -e esp32-s3-devkitc-1
```

See [`docs/firmware/architecture.md`](docs/firmware/architecture.md) for the
task layout and [`docs/firmware/data-format-spec.md`](docs/firmware/data-format-spec.md)
for the on-card record format.

### Analysis

```
python -m venv .venv && . .venv/bin/activate
pip install -e analysis/
pytest analysis/tests
```

### Installing on a machine

Read [`docs/safety.md`](docs/safety.md) before touching a machine. Then
follow the model-specific procedure in
[`docs/install-guides/137A.md`](docs/install-guides/137A.md).

## Project status

**M0 — docs and repo skeleton.** No hardware has been built or bench-tested
yet; this stage is establishing the architecture, decisions, and safety
constraints the rest of the project builds on.

Milestones:

- **M0** — Docs and skeleton. Architecture, ADRs, safety doc, roadmap; repo
  layout in place. *(current)*
- **M1** — Bench bring-up of real drivers: each sensor/breakout talking to
  the ESP32-S3 on a breadboard, no enclosure, no machine.
- **M2** — Enclosure integration: logger core assembled in its IP65 box,
  sensor pods wired and connectorized, full firmware pipeline exercised on
  the bench.
- **M3** — Bench test on a spare 137A: full install procedure rehearsed on a
  non-production machine.
- **M4** — First field deployment: unit installed in a live machine at a
  customer site for a real diagnostic case.
- **M5** — 117A/127A validation: confirm the sensor placements and
  thresholds generalize across the other two chassis sizes.

See [`docs/roadmap.md`](docs/roadmap.md) for what comes after M5.
