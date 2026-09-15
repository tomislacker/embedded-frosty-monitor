# ADR 0003: ESP32-S3-DevKitC-1 as the compute platform

## Status

Accepted

## Context

The logger core needs to run several concurrent sampling tasks, buffer
vibration bursts large enough that they don't fit comfortably in a
typical microcontroller's internal RAM, and — per
[docs/roadmap.md](../roadmap.md) — eventually support BLE-to-phone offload
and WiFi/cloud upload without a platform change. The realistic
alternatives considered were an RP2350-based board and an STM32-based
board.

## Decision

Use an ESP32-S3-DevKitC-1 with 8MB of PSRAM as the compute platform, as a
dev board plus off-the-shelf breakouts — no custom PCB in the near term.

## Consequences

The S3 has WiFi and BLE built in, so the BLE-to-phone and WiFi/cloud
offload items on the roadmap are a firmware-only lift later, not a
hardware redesign. The PSRAM gives `VibrationCaptureTask` a ring buffer
large enough to hold raw burst data without starving other tasks of
internal RAM. The Arduino/ESP-IDF ecosystem around this chip is mature,
which matters directly for
[ADR 0005](0005-firmware-framework-platformio-arduino.md).

Sticking to a dev board plus breakouts instead of a custom PCB keeps M0-M2
hardware iteration cheap and fast, at the cost of a bulkier, less
integrated enclosure than a custom board would allow. That tradeoff is
acceptable while the unit is portable and low-volume; a cost- and
size-reduced custom PCB is explicitly deferred to the v2 permanent-install
monitor (see [docs/roadmap.md](../roadmap.md)).
