#include "leak_sensors.h"

#include <cmath>

namespace {

// Stub drop cadence: a base period with a slow sinusoidal wobble so the
// rate isn't perfectly flat, deterministic in `now_ms` (no Arduino
// millis()/random() calls -- see the file-level note on why this stays
// Arduino-free).
constexpr uint32_t kBaseDropPeriodMs = 7000;
constexpr uint32_t kDropJitterMs = 1500;

} // namespace

// ---- DripRateMonitor: real windowed rate-counting logic ----

void DripRateMonitor::recordDrop(uint32_t now_ms) {
    dropTimes_[writeIdx_] = now_ms;
    writeIdx_ = (writeIdx_ + 1) % kMaxDropsTracked;
    if (count_ < kMaxDropsTracked) {
        ++count_;
    }
}

uint16_t DripRateMonitor::dropCountInWindow(uint32_t now_ms) const {
    uint16_t inWindow = 0;
    for (size_t i = 0; i < count_; ++i) {
        // Unsigned subtraction wraps correctly across millis() rollover as
        // long as the drop is not more than ~2^31 ms in the past, which is
        // always true here since we only ever look back kWindowMs.
        const uint32_t age = now_ms - dropTimes_[i];
        if (age <= kWindowMs) {
            ++inWindow;
        }
    }
    return inWindow;
}

float DripRateMonitor::dripsPerMinute(uint32_t now_ms) const {
    const uint16_t inWindow = dropCountInWindow(now_ms);
    return static_cast<float>(inWindow) * (60000.0f / static_cast<float>(kWindowMs));
}

// ---- LeakSensorsHal: STUB(M1) synthetic drop source + fake add-on reads ----

LeakSensorsHal::LeakSensorsHal() = default;

bool LeakSensorsHal::begin() {
    healthy_ = true;
    return true;
}

bool LeakSensorsHal::healthy() const {
    return healthy_;
}

const char* LeakSensorsHal::name() const {
    return "leak_sensors(stub)";
}

void LeakSensorsHal::tickStub(uint32_t now_ms) {
    lastNowMs_ = now_ms;
    if (now_ms >= nextDropDueMs_) {
        dripMonitor_.recordDrop(now_ms);
        const uint32_t jitter =
            static_cast<uint32_t>(static_cast<float>(kDropJitterMs) *
                                   (0.5f + 0.5f * sinf(static_cast<float>(now_ms) / 9000.0f)));
        nextDropDueMs_ = now_ms + kBaseDropPeriodMs + jitter;
    }
}

float LeakSensorsHal::dripRateCpm() const {
    return dripMonitor_.dripsPerMinute(lastNowMs_);
}

float LeakSensorsHal::moistureRaw() const {
    if (!moisturePresent_) {
        return NAN; // configured absent
    }
    const float t = static_cast<float>(lastNowMs_) / 1000.0f;
    // Dry pad most of the time: wanders low and slow, clamped to 0.0-1.0.
    float v = 0.12f + 0.05f * sinf(t * 0.05f) + 0.02f * sinf(t * 0.37f + 1.1f);
    if (v < 0.0f) v = 0.0f;
    if (v > 1.0f) v = 1.0f;
    return v;
}

float LeakSensorsHal::refrigerantRaw() const {
    if (!refrigerantPresent_) {
        return NAN; // configured absent
    }
    const float t = static_cast<float>(lastNowMs_) / 1000.0f;
    // Low background reading in the compressor compartment, uncalibrated.
    float v = 0.08f + 0.03f * sinf(t * 0.09f + 0.4f) + 0.01f * sinf(t * 0.6f);
    if (v < 0.0f) v = 0.0f;
    if (v > 1.0f) v = 1.0f;
    return v;
}

void LeakSensorsHal::setMoisturePresent(bool present) {
    moisturePresent_ = present;
}

void LeakSensorsHal::setRefrigerantPresent(bool present) {
    refrigerantPresent_ = present;
}
