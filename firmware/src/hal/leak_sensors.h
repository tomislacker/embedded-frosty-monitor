// leak_sensors.h - leak-detection channels: drip-tube drop counter (DRIP_PULSE)
// plus two optional add-on ADS1115 channels (moisture pad, refrigerant gas).
//
// The IR slot-type optical sensor at pins::DRIP_PULSE outputs one pulse per
// drop at the machine's drip tube (rear-seal product-leak telltale). Looking
// at raw drop timestamps one at a time is noisy for trending, so presence
// and severity are reported as a rolling drips-per-minute rate instead.
//
// DripRateMonitor below is the real windowed rate-counting logic, written
// for real now (pure, no Arduino deps) because it's fully unit-testable --
// same pattern as DigitalInputMonitor in digital_input.h. Only the drop
// *source* is stubbed for M0: LeakSensorsHal::tickStub() synthesizes
// occasional drops. The M1 replacement wires a real GPIO ISR that calls
// DripRateMonitor::recordDrop() directly; the rate-counting logic itself
// does not change.
//
// The moisture pad (ADS1115 A2) and refrigerant gas sensor (ADS1115 A3,
// EXPERIMENTAL/uncalibrated) are both optional add-on hardware -- some
// deployments won't have them wired. moistureRaw()/refrigerantRaw() return
// NAN when configured absent, same "missing sensor" convention as
// temp_ds18b20's hopper channel.
#pragma once

#include <cstddef>
#include <cstdint>

#include "i_sensor.h"

class DripRateMonitor {
public:
    // Rolling window length used to compute the drips-per-minute rate.
    // Shorter than a full minute so the reported rate tracks a change in
    // drip severity within tens of seconds rather than lagging a full
    // minute behind.
    static constexpr uint32_t kWindowMs = 30000;
    // Per-channel drop history depth. Sized generously relative to a worst-
    // case active leak (several drops/sec) so the window is never
    // drop-count-starved.
    static constexpr size_t kMaxDropsTracked = 128;

    DripRateMonitor() = default;

    // Records one drop observed at `now_ms` (millis()-style, monotonically
    // increasing, wraparound-safe). Called from the GPIO ISR (real M1 impl)
    // or the stub's synthetic drop generator.
    void recordDrop(uint32_t now_ms);

    // Number of drops retained that fall within the window ending at
    // `now_ms`. Exposed mainly for unit tests.
    uint16_t dropCountInWindow(uint32_t now_ms) const;

    // Drops-per-minute rate, extrapolated from dropCountInWindow() over
    // kWindowMs, evaluated as of `now_ms`.
    float dripsPerMinute(uint32_t now_ms) const;

private:
    uint32_t dropTimes_[kMaxDropsTracked] = {0};
    size_t writeIdx_ = 0;
    size_t count_ = 0; // valid entries in dropTimes_, <= kMaxDropsTracked
};

// STUB(M1): real replacement wires a GPIO ISR on pins::DRIP_PULSE that calls
// DripRateMonitor::recordDrop() directly (the windowed rate logic above is
// reused unchanged), plus single-ended ADS1115 reads on
// ads1115_channel::MOISTURE_PAD / REFRIGERANT_GAS (pins.h) scaled to
// 0.0-1.0.
class LeakSensorsHal : public ISensor {
public:
    LeakSensorsHal();

    bool begin() override;
    bool healthy() const override;
    const char* name() const override;

    // Advances the stub drop simulation and the underlying DripRateMonitor
    // to `now_ms`. Call once per 1Hz sampling tick in place of a real GPIO
    // ISR. `now_ms` should be a monotonically increasing millis()-style
    // clock.
    void tickStub(uint32_t now_ms);

    // Rolling drip rate (drops/minute) as of the most recent tickStub() call.
    float dripRateCpm() const;

    // Moisture pad reading, normalized 0.0-1.0, uncalibrated. NAN if
    // configured absent (setMoisturePresent(false)).
    float moistureRaw() const;

    // Refrigerant gas sensor reading, normalized 0.0-1.0, EXPERIMENTAL and
    // uncalibrated -- never present this as calibrated ppm. NAN if
    // configured absent (setRefrigerantPresent(false)).
    float refrigerantRaw() const;

    // Configures whether the optional add-on sensors are present. Both
    // default to true (stub simulates them wired) since they're the
    // exception rather than the rule; the real M1 driver would instead
    // reflect config.json / an ADS1115 probe result.
    void setMoisturePresent(bool present);
    void setRefrigerantPresent(bool present);

private:
    DripRateMonitor dripMonitor_;
    uint32_t nextDropDueMs_ = 0;
    uint32_t lastNowMs_ = 0;
    bool healthy_ = false;
    bool moisturePresent_ = true;
    bool refrigerantPresent_ = true;
};
