# Firmware architecture

This document describes how the frosty-monitor firmware is structured: the
task layout, the buses and drivers each task owns, and the constraints that
shape the FreeRTOS design. For *why* this platform and framework were chosen,
see [ADR 0003](../adr/0003-esp32-s3-devkitc-1-platform.md) (ESP32-S3) and
[ADR 0005](../adr/0005-firmware-framework-platformio-arduino.md) (PlatformIO
+ Arduino core). For the hardware each task talks to, see
[docs/architecture/overview.md](../architecture/overview.md). For the on-card
record shapes referenced throughout, see
[data-format-spec.md](data-format-spec.md). For the pin-level wiring, the
single source of truth is `firmware/src/pins.h`, mirrored in
[docs/hardware/wiring-and-pinmap.md](../hardware/wiring-and-pinmap.md).

## Platform

PlatformIO project targeting an ESP32-S3-DevKitC-1 (8MB PSRAM), built on the
Arduino core for ESP32 (arduino-esp32). Concurrency is handled with FreeRTOS
APIs directly — tasks, queues, and a mutex — rather than relying on the
Arduino `loop()` model. See [ADR 0005](../adr/0005-firmware-framework-platformio-arduino.md)
for the rationale behind PlatformIO + Arduino over raw ESP-IDF.

## Task layout

All tasks are created with `xTaskCreatePinnedToCore`. Priority is listed
highest first; higher-priority tasks preempt lower ones, which is why the
timing-sensitive vibration capture sits above the 1Hz scheduler, which sits
above storage, which sits above UI.

| Task | Priority | Role |
|---|---|---|
| `VibrationCaptureTask` | 4 (highest) | Windowed burst sampling of both ADXL345 pods |
| `SamplingSchedulerTask` | 3 | 1Hz current/temp/digital sampling, trigger detection |
| `StorageWriterTask` | 2 | Single consumer of the record queue, writes to the active `IStorageSink` |
| `UITask` | 1 (lowest) | Button debounce, event journaling, LED policy |

`ConfigLoader` is not an always-on task in this table: it runs at boot to
seed configuration and time, then hands off to an idle serial CLI on UART0
for the rest of the unit's life (see [ConfigLoader](#configloader-boot--cli)
below).

### VibrationCaptureTask (priority 4)

Highest priority because vibration sampling is timing-sensitive: sample
jitter directly corrupts the FFT band-energy computation. This task:

- Captures both ADXL345 pods in windowed bursts, targeting 1.6–3.2kHz per
  axis, 2-second bursts, on a schedule of once every 5 minutes plus
  on-trigger (triggered by `SamplingSchedulerTask` — see below).
- Buffers raw samples in a ring buffer allocated in PSRAM
  (`heap_caps_malloc(..., MALLOC_CAP_SPIRAM)`), since a raw burst at these
  sample rates does not fit comfortably in the ESP32-S3's internal RAM
  alongside everything else running.
- Computes, per burst, RMS, peak, and three FFT band energies — bands
  5–50Hz, 50–300Hz, 300–800Hz — using ESP-DSP.
- **Always** enqueues the lightweight summary record (RMS/peak/band-energy)
  for every burst. The raw burst itself is only enqueued periodically and
  on trigger, not for every window — raw bursts are far larger and the
  summary is what's cheap enough to keep at high frequency. See the storage
  budget table below for why this split matters.

### SamplingSchedulerTask (priority 3)

A 1Hz loop that is the source of the channel CSV row and the trigger logic:

- Reads both current channels off the ADS1115 (RMS computed over one AC-cycle
  window, not a single instantaneous sample).
- Reads temperatures: DS18B20s via async (non-blocking) conversion so the
  ~750ms 1-Wire conversion time doesn't stall the 1Hz loop, plus the
  MAX31855 thermocouple.
- Reads digital control-state (AC-presence inputs; see the edge-counting
  constraint below).
- Emits exactly one `ChannelRow` record per second onto the FreeRTOS record
  queue.
- Evaluates trigger conditions — e.g., a compressor-start current spike —
  and on trigger, requests both a vibration burst from
  `VibrationCaptureTask` and a current transient capture, so a single event
  is captured from more than one sensing axis at once.

### StorageWriterTask (priority 2)

The **single consumer** of one FreeRTOS record queue — every other task only
ever produces records onto this queue, never touches storage directly. This
task:

- Formats each record according to [data-format-spec.md](data-format-spec.md)
  (exact CSV headers, JSONL shape, binary vibration format).
- Writes through the `IStorageSink` interface. The MVP ships exactly one
  implementation, `SdSink`; see [Storage abstraction](#storage-abstraction-istoragesink)
  below.
- Rotates output files daily (new `channels_YYYYMMDD.csv`,
  `events_YYYYMMDD.jsonl`, `vib_summary_YYYYMMDD.csv` at each UTC day
  boundary).
- Flushes/fsyncs on a tunable cadence — roughly every 5 seconds or every N
  records, whichever comes first. This cadence is the direct knob on
  power-loss exposure: the unflushed window is the maximum data a sudden
  power loss can cost. See [Power-loss resilience](#power-loss-resilience)
  below.

Being the sole owner of SD/SPI access is deliberate, not incidental — see the
[SPI bus sharing](#spi-bus-sharing-sd-and-max31855) constraint below.

### UITask (priority 1)

Lowest priority; nothing here is timing-critical relative to sampling or
storage.

- Debounces the physical event-journal button. A press is treated as a
  complete, point-in-time incident report on its own — it does not block
  waiting for any annotation — and is pushed as an `Event` record with
  `type=button`. Later enrichment (QR-scanned description, photos) is
  correlated out of band; see
  [data-flow.md](../architecture/data-flow.md#walkthrough-a-journal-button-press).
- Owns LED policy: heartbeat blink while recording is healthy, a
  solid/pattern indication on error, and a distinct pattern for card-capacity
  warnings.

### ConfigLoader (boot + CLI)

Not a persistent FreeRTOS task in the priority table above — it runs at boot,
then the rest of its life is an idle serial CLI on UART0:

- At boot, reads `/config.json` from the SD card (deployment metadata,
  sample-rate/burst overrides).
- Seeds `settimeofday()` from the DS3231 RTC. **The RTC is the time source of
  truth** for the unit — it is set once at bench provisioning via the CLI
  `SETTIME` command (e.g. `SETTIME 2026-09-14T10:00:00Z`) and carries a coin
  cell across power cycles and transport. The ESP32-S3 itself has no
  battery-backed clock of its own.
- Echoes the effective, resolved configuration into `manifest.json` at
  deployment start, so the card is self-describing even if `config.json` is
  later lost, edited, or never matched what actually ran.
- Exposes an idle-time serial CLI on UART0 for bench and field use:
  - `SETTIME <ISO-8601 UTC>` — set the DS3231.
  - `STATUS` — report recording state, free card space, last-record
    timestamps.
  - `ID <deployment fields>` — set deployment ID, machine model, machine
    serial, technician, and any other manifest identity fields.

## Key implementation constraints

These four constraints shaped the task design above and are easy to get
wrong if re-derived from scratch, so they're documented explicitly here.

### AC-presence edge counting, not digitalRead

The AC-presence opto inputs conduct once per AC half-cycle. While a given
node is energized, the GPIO the opto drives sees a **line-frequency pulse
train**, not a steady level — a naive `digitalRead()` samples an
essentially random point in that pulse train and is wrong more often than
not.

The `digital_input` HAL must instead **count edges in a rolling ~100ms
window** and declare the input on/off by comparing the edge count against a
threshold (a live 60Hz line produces roughly 12 edges in 100ms; near-zero
edges means the node is not energized). This is implemented as a HAL-level
concern so `SamplingSchedulerTask` only ever sees a debounced boolean state,
never raw pulses.

### SPI bus sharing: SD and MAX31855

SD/SPI access is **single-task-only by design** — only `StorageWriterTask`
talks to the SD card, which is also why it's the sole record-queue consumer
in the first place. But the MAX31855 thermocouple amplifier shares the same
physical SPI bus, and it's read from `SamplingSchedulerTask` once per 1Hz
tick.

The chosen approach is a **SPI bus mutex** with short transactions:

- A single FreeRTOS mutex guards the physical SPI bus.
- `SamplingSchedulerTask` takes the mutex, does its (short, single-transfer)
  MAX31855 read, releases it.
- `StorageWriterTask` takes the same mutex around SD writes, but only holds
  it **per block**, not for the duration of a whole file write, so it never
  starves the thermocouple read for more than one block's worth of time.

This was chosen over the MVP-simplification alternative of marshalling
thermocouple reads through a request into the storage task's own context
(i.e., having `StorageWriterTask` do the MAX31855 read on
`SamplingSchedulerTask`'s behalf) because the mutex approach keeps the
thermocouple reading logic in the task that owns the rest of the 1Hz sample,
rather than splitting one logical sample across two tasks.

### Power-loss resilience

There is no logger-core battery; only the DS3231 RTC has its own coin cell.
A power loss (unit unplugged, outlet trips, field mishap) can happen with no
graceful shutdown. Mitigations, all reflected in `StorageWriterTask`'s
behavior above:

- **Append-only writes** — records are appended to open files, never
  rewritten in place, so a torn write can't corrupt already-flushed data.
- **Bounded fsync cadence** (~5s or N records) — caps the unflushed window,
  trading a small amount of flash wear and I/O overhead for a bounded
  worst-case data loss on power loss.
- **Daily file rotation** — bounds the blast radius of a corrupted tail to
  one day's file, not the whole deployment.
- **`manifest.json` written at deployment start** — so even a card pulled
  moments after a power loss still identifies the deployment, machine, and
  effective config, not just orphaned channel rows.

### Storage abstraction: IStorageSink

All record emission from `StorageWriterTask` goes through one interface:

```cpp
class IStorageSink {
public:
    virtual bool write(const SampleRecord&) = 0;
    virtual void flush() = 0;
    virtual bool isReady() const = 0;
};
```

`SdSink` is the only implementation in the MVP. The interface exists so that
a future BLE or WiFi transport is a **new sink implementation**, not a
rewrite of any sampling or scheduling code — no task upstream of
`StorageWriterTask` knows or cares which sink is active. See
[ADR 0002](../adr/0002-microsd-storage-with-transport-abstraction.md) and
[data-flow.md](../architecture/data-flow.md#where-ble-and-cloud-offload-fit).

## Storage budget

Approximate daily storage consumption, assuming the default sample rates and
burst cadence described above:

| Source | Rate / size | Approx. daily volume |
|---|---|---|
| `ChannelRow` CSV (1Hz) | ~120 bytes/row × 86,400 rows/day | ≈ 10 MB/day |
| Vibration bursts (periodic) | 2 pods × 3 axes × 2s @ 1600Hz int16, every 5 min | ≈ 11 MB/day |
| Triggered transients (current + vibration) | occasional, event-driven | < 1 MB/day |
| Events (JSONL) | button/system/trigger/error, negligible payload | negligible |
| **Total** | | **≈ 25–30 MB/day** |

A 32GB card at that rate lasts on the order of years; the actual deployment
window per install is weeks (see [ADR 0001](../adr/0001-portable-daq-first.md)),
so there is a large margin. That margin is intentional headroom, not waste:
if a failure signature under investigation needs a higher burst rate or
longer bursts, that can be raised at bench provisioning without threatening
card capacity for the deployment window.

## Pin map

The pin map is not duplicated here. `firmware/src/pins.h` is the single
source of truth, mirrored for humans in
[docs/hardware/wiring-and-pinmap.md](../hardware/wiring-and-pinmap.md). Key
assignments, for quick reference while reading this document:

| Function | Pin(s) |
|---|---|
| I2C (ADS1115, DS3231, P82B715 → ADXL345 pods) | GPIO 8/9 |
| SPI (SD + MAX31855, shared bus) | GPIO 11/12/13 |
| SD chip select | GPIO 10 |
| MAX31855 chip select | GPIO 14 |
| 1-Wire (DS18B20 chain) | GPIO 4 |
| AC-presence opto inputs | GPIO 15/16/17/18 |
| Buttons | GPIO 6/7 |
| Status LEDs | GPIO 1/2/5 |

Treat this table as a convenience cross-check only — if it and
`firmware/src/pins.h` ever disagree, `pins.h` wins.
