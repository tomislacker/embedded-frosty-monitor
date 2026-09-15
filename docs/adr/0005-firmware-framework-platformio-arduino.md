# ADR 0005: PlatformIO plus the Arduino core over raw ESP-IDF

## Status

Accepted

## Context

Firmware needs drivers for a handful of off-the-shelf breakouts — ADS1115,
ADXL345, MAX31855, DS18B20/OneWire, DS3231 — plus real concurrency
across multiple sampling tasks, a single-consumer storage writer, and
(eventually) BLE. The two realistic framework choices on the ESP32-S3 are
raw ESP-IDF, or PlatformIO with the Arduino core (arduino-esp32) on top of
it.

## Decision

Use PlatformIO with the Arduino core. Every breakout in the BOM already
has a mature Arduino library — Adafruit's ADS1X15, ADXL345, and MAX31855
libraries, OneWire/DallasTemperature for the DS18B20 chain, RTClib for the
DS3231 — and arduino-esp32 does not hide FreeRTOS or ESP-IDF underneath it:
`xTaskCreatePinnedToCore`, `heap_caps_malloc` with `MALLOC_CAP_SPIRAM`, and
the rest of the ESP-IDF API surface remain directly usable.

## Consequences

This is not really a tradeoff between "easy drivers" and "real control" —
it's Arduino's driver ecosystem plus FreeRTOS's task/queue model
underneath, at the same time. Task structure described in
[data-flow.md](../architecture/data-flow.md) (`VibrationCaptureTask`,
`SamplingSchedulerTask`, `StorageWriterTask`, `UITask`) is written directly
against FreeRTOS primitives, not an Arduino `loop()`. Future BLE work is
covered by NimBLE-Arduino, keeping the same story for that addition.

The one thing this does defer: if flash size or power budget get tight on
the v2 permanent-install monitor (see [docs/roadmap.md](../roadmap.md)),
the Arduino core's overhead relative to raw ESP-IDF is worth revisiting
then. It is not a concern at MVP scale.
