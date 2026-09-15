# frosty-monitor firmware

Portable diagnostic DAQ firmware for the ESP32-S3-DevKitC-1 (8MB octal
PSRAM). Logs sensor data to microSD for later offline analysis.

**M0 status (this milestone):** the full task pipeline (sampling -> queue ->
SD writer, plus vibration capture and UI) compiles, links, and runs with
**stub sensor drivers** -- no hardware attached, every reading is a
plausible fake. Real drivers land at M1 bench bring-up. See the stub table
below for exactly what's fake today.

## Build / flash / monitor

```sh
cd firmware
pio run -e esp32-s3-devkitc-1          # build
pio run -e esp32-s3-devkitc-1 -t upload  # flash (board attached via USB)
pio device monitor -b 115200             # serial monitor
```

First build downloads the espressif32 platform + Xtensa toolchain (several
hundred MB); subsequent builds are fast (a couple of seconds, as seen
above).

### Native unit tests

Pure-logic modules (CSV/JSON/binary formatting, the ring buffer, the
digital-input windowed-detection logic, and the leak-sensor drip-rate
rolling-window logic) have no Arduino dependency and are unit tested on the
host:

```sh
cd firmware
pio test -e native
```

This was run in the environment that produced this skeleton and passed (20
test cases). If your host toolchain can't build the `native` platform (e.g.
no gcc/g++ available), the `esp32-s3-devkitc-1` build above is the load-
bearing one -- native is a convenience for fast local iteration on
formatting/logic bugs.

### Serial CLI

While running, the firmware accepts two commands over the serial monitor
(newline-terminated):

- `SETTIME <iso8601>` -- e.g. `SETTIME 2026-09-14T12:00:00Z`; sets the
  system clock (this is what the DS3231 stub's `now_ms()` reads from).
- `STATUS` -- prints firmware version, current time, SD-card readiness, and
  the effective config.

## Stub driver status (M0)

Every stub is marked in source with `// STUB(M1): <replacement>`. None of
them touch real hardware buses yet (no I2C/SPI/1-Wire transactions) except
`sd_sink.cpp`, which does real SD SPI I/O -- the pipeline is expected to
run on a bare devkit with no sensors attached, only optionally with a
microSD card.

| Module | Stub behavior | M1 replacement |
|---|---|---|
| `hal/current_sensor_ads1115` | Beater wanders ~2-4A continuously; compressor is a fake ~50s on/40s off duty cycle, ~0A off / ~6-8A on | Adafruit_ADS1X15 over I2C (`i2c_addr::ADS1115`), CT burden-resistor scaling |
| `hal/vibration_adxl345` | `fillBurst()` synthesizes sine (distinct freq/amplitude per pod) + noise into the interleaved XYZ int16 buffer | Adafruit_ADXL345_U / raw FIFO burst read over I2C (`ADXL345_POD_A`/`_POD_B`) |
| `hal/temp_ds18b20` | Cylinder/cond-in/cond-out/ambient wander slowly around plausible values; hopper channel always returns NAN (models an unpopulated probe) | OneWire + DallasTemperature enumeration on `pins::ONEWIRE_BUS` |
| `hal/temp_thermocouple_max31855` | Wanders 75-95C when the (stub) compressor is "on", relaxes toward ambient when off | MAX31855 SPI frame decode on `pins::MAX31855_CS`, fault-bit surfacing via `healthy()` |
| `hal/digital_input` | `DigitalInputMonitor` (the windowed edge-count detector) is **real, unit-tested logic**, not stubbed. Only the edge *source* is fake: `DigitalInputHal::tickStub()` synthesizes a per-channel duty-cycle pulse train | GPIO ISRs on `ACSENSE_*` pins call `DigitalInputMonitor::recordEdge()` directly; detection logic unchanged |
| `hal/leak_sensors` | `DripRateMonitor` (the rolling-window drops-per-minute counter) is **real, unit-tested logic**, not stubbed. Only the drop *source* is fake: `LeakSensorsHal::tickStub()` synthesizes occasional drops; moisture/refrigerant reads wander around plausible low values (or return `NAN` if `set{Moisture,Refrigerant}Present(false)`) | GPIO ISR on `pins::DRIP_PULSE` calls `DripRateMonitor::recordDrop()` directly (rate logic unchanged); real ADS1115 single-ended reads on `ads1115_channel::MOISTURE_PAD`/`REFRIGERANT_GAS` |
| `hal/rtc_ds3231` | Wraps libc `time()`/`settimeofday()`; seeds a fixed time if the clock looks unset (pre-2023) | DS3231 I2C read/write (`i2c_addr::DS3231`), used to discipline the system clock at boot |

Adafruit sensor libraries are **deliberately not** a dependency yet -- the
only external lib in `platformio.ini` is `bblanchon/ArduinoJson`, used by
`config_loader` for `config.json`/`manifest.json`. Adafruit_ADS1X15,
Adafruit_ADXL345_U, OneWire/DallasTemperature, Adafruit_MAX31855, and
RTClib (or equivalents) are added at M1 alongside the real drivers they
back.

Vibration band-energy computation (`tasks/vibration_capture.cpp`) is
likewise a placeholder: it splits each burst into three equal time chunks
and sums squared magnitude per chunk, labeled low/mid/high. This is **not**
a real frequency-domain decomposition -- it exists so the summary CSV has
plausible values to validate the pipeline against. Real Goertzel/FFT-based
band energy via `esp-dsp` is M1 scope.

## How to add a real driver (M1 checklist)

1. Add the vendor library to `lib_deps` in `platformio.ini`.
2. Implement the real I2C/SPI/1-Wire transactions in the existing stub's
   `.cpp` file (keep the class/method signatures the same where possible --
   `tasks/*` code shouldn't need to change). Update `begin()` to actually
   probe the device and `healthy()` to reflect real bus/fault state.
3. Delete the `// STUB(M1):` comment and the synthetic-data helper
   functions.
4. If the driver does SPI I/O and shares the bus with SD (MAX31855 does --
   see `pins.h`), guard every transaction with `sdSpiMutex()` from
   `storage/sd_sink.h`, the same mutex `sd_sink.cpp` already uses. Don't add
   a second mutex.
5. Digital inputs specifically: swap `DigitalInputHal`'s stub tick loop for
   real `attachInterrupt()` ISRs on `ACSENSE_*` that call
   `DigitalInputMonitor::recordEdge(channel, millis())`. The windowed
   detection logic (`DigitalInputMonitor::isActive`) does not change and is
   already unit tested in `test/test_native/test_main.cpp`.
6. Leak sensors specifically: swap `LeakSensorsHal`'s stub tick loop for a
   real `attachInterrupt()` ISR on `pins::DRIP_PULSE` that calls
   `DripRateMonitor::recordDrop(millis())`, and replace `moistureRaw()`/
   `refrigerantRaw()` with real ADS1115 single-ended reads on
   `ads1115_channel::MOISTURE_PAD`/`REFRIGERANT_GAS`. The rolling-window rate
   logic (`DripRateMonitor::dripsPerMinute`) does not change and is already
   unit tested in `test/test_native/test_main.cpp`.
7. Run `pio test -e native` (still green -- you shouldn't have touched
   anything it covers) and `pio run -e esp32-s3-devkitc-1` (build), then
   bench-verify against the real sensor.

## Data format (v1)

Implemented by `src/storage/record_format.{h,cpp}` (pure functions, no
Arduino headers, unit tested natively) and written to disk by
`src/storage/sd_sink.cpp`.

- `channels_YYYYMMDD.csv` -- 1 row/second. Header:
  `ts_iso,ts_unix_ms,current_beater_a,current_compressor_a,temp_cylinder_c,temp_cond_in_c,temp_cond_out_c,temp_ambient_c,temp_hopper_c,temp_discharge_c,beater_on,compressor_cmd,tcc_satisfied,hp_ok,drip_rate_cpm,moisture_raw,refrigerant_raw`
  (the last three columns -- `drip_rate_cpm`, `moisture_raw`,
  `refrigerant_raw` -- are a v1.1 non-breaking addition; see
  [docs/firmware/data-format-spec.md](../docs/firmware/data-format-spec.md#v11-additions))
  Floats are plain decimal (`%.3f`); NaN/missing -> empty field; bools are
  `0`/`1`; `ts_iso` is UTC ISO-8601.
- `vibration/vib_summary_YYYYMMDD.csv` -- one row per vibration capture.
  Header:
  `ts_iso,ts_unix_ms,pod_id,rms_x_g,rms_y_g,rms_z_g,peak_x_g,peak_y_g,peak_z_g,band_low_g2,band_mid_g2,band_high_g2`
- `events_YYYYMMDD.jsonl` -- one JSON object per line:
  `{"ts_iso":...,"ts_unix_ms":...,"type":"button"|"system"|"trigger"|"error","detail":{...}}`
- `vibration/vib_<pod>_<ts_unix_ms>.bin` -- 32-byte little-endian header
  (magic `FVB1`, version, pod_id, sample rate, sample count, axis count,
  start timestamp, LSB scale -- see `record_format.h` for the exact byte
  offsets) followed by `n_samples * 3` interleaved `int16_t` XYZ samples.
- `manifest.json` -- `{"schema_version":1,"deployment_id","machine_model","machine_serial","technician","firmware_version","start_ts_iso","channel_map":{},"config_effective":{}}`,
  written once at boot from `config.json` + defaults.
- `config.json` -- optional; read at boot, defaults applied for anything
  missing/absent (including when the card itself is absent).

All of the above rotates daily by filename (`_YYYYMMDD` suffix); rotation
is handled transparently inside `SdStorageSink` -- `storage_writer` just
calls `sink->write()`/`sink->flush()` and doesn't know about file rotation.

## Cloud connectivity (premium tier, disabled by default)

`StorageWriterTask` tees every record to a small array of sinks, not just
SD: `storage/cloud_sink.{h,cpp}` implements `IStorageSink` and best-effort
mirrors aggregated channel/vibration data plus events to an MQTT broker over
TLS. It's **disabled by default** -- with no `"cloud"` object in
`config.json` (or `"cloud":{"enabled":false}`), it touches no WiFi hardware
at all and costs nothing. `storage/ble_sink.h` is a header-only stub for the
lower-tier BLE walk-up offload design (documented, not implemented).

To enable on the bench: drop `ca.pem`/`device.pem`/`device.key` at
`/certs/` on the SD card (see `cloud/README.md`'s provisioning script for
generating a dev set), and add a `"cloud"` object to `/config.json`, e.g.:

```json
{
  "cloud": {
    "enabled": true,
    "wifi_ssid": "bench-wifi",
    "wifi_pass": "...",
    "mqtt_host": "test.mosquitto.example",
    "client_id": "bench-unit-01"
  }
}
```

See [docs/firmware/connectivity.md](../docs/firmware/connectivity.md) for
the full design: the multi-sink tee, `CloudSink`'s connection state machine,
publish topics/JSON schemas, TLS cert provisioning, the watermark/backfill
plan (M2), and the BLE roadmap.

## Architecture notes

- **Single writer, multiple sinks.** Only `tasks/storage_writer` calls
  `IStorageSink::write()`/`flush()`; every other task only ever pushes a
  `SampleRecord` onto the shared FreeRTOS queue (`AppContext::sampleQueue`).
  It tees each record to every sink in `AppContext::sinks` (SD, then Cloud,
  then BLE -- see [Cloud connectivity](#cloud-connectivity-premium-tier-disabled-by-default)
  above), but SD is still the only one doing real card I/O in the MVP/M0/M1
  sense, so SD access never needs cross-task locking beyond the SPI-bus
  mutex (`sdSpiMutex()`), which exists purely to keep SD and MAX31855
  electrically off each other's toes on the shared SPI bus (`pins.h`).
- **Cardless operation.** `SdStorageSink::begin()`/`isReady()` return
  `false` if no card is present or mounting fails; `write()` then logs to
  Serial and returns `false` without touching the filesystem. Nothing in
  the pipeline crashes or blocks on a missing card, and a hot-inserted card
  is picked up automatically (`write()` retries `SD.begin()` opportunistically).
- **VibBurst buffer ownership.** `vibration_capture` allocates the raw
  sample buffer with `heap_caps_malloc(..., MALLOC_CAP_SPIRAM)` (falling
  back to `malloc()` if PSRAM alloc fails, which is also what makes the
  same code path link host-side, e.g. under `pio test -e native` if you
  ever pull that file into a native-testable target). Ownership of the
  pointer transfers into the `SampleRecord` queue message; whichever code
  path stops passing it along (successful write in `sd_sink.cpp`, a full
  queue in `vibration_capture.cpp`, or a cardless `write()` in
  `sd_sink.cpp`) is responsible for `free()`-ing it. See the comment on
  `VibBurst` in `storage/record_types.h` for the authoritative statement of
  this contract. `CloudSink`/`BleSink` never publish raw bursts and never
  touch `VibBurst::data` at all -- SD remains the sole owner/freer even
  though every sink now sees the same record.
- **AppContext.** `src/app_context.h` bundles every HAL stub pointer, the
  sample queue, and the config loader into one struct so task functions
  take a single `AppContext*` as their FreeRTOS task parameter instead of a
  pile of `extern` globals. Constructed once in `main.cpp::setup()`.

## Platform-version quirks discovered

- `board_build.arduino.memory_type = qio_opi` (the spec's first choice)
  builds successfully against the pinned `espressif32` platform version
  (7.1.3, with `framework-arduinoespressif32 @ 4.20017.260907`) -- the
  `opi_opi` fallback mentioned in the spec was not needed.
- PlatformIO's board metadata for `esp32-s3-devkitc-1` prints as
  `Espressif ESP32-S3-DevKitC-1-N8 (8 MB QD, No PSRAM)` in build output.
  That's just the generic board JSON description text; it does not reflect
  `-DBOARD_HAS_PSRAM`/`memory_type=qio_opi` actually being applied (verified
  present in the real compiler invocation via `pio run -v`). Don't be
  alarmed by "No PSRAM" in that banner.
- ArduinoJson 7.4.3 (resolved from the `^7.1.0` constraint) deprecates
  `StaticJsonDocument<N>` and `createNestedObject()` in favor of
  `JsonDocument` and `doc[key].to<JsonObject>()`; `config_loader.cpp` uses
  the current API directly to avoid deprecation warnings.
