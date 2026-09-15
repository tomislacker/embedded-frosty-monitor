// digital_input.h - AC-presence detection on opto pulse-train inputs.
//
// The opto isolators wired to ACSENSE_* pins (see pins.h) output a train of
// short pulses only while AC line voltage is present on the sensed circuit
// (beater run winding, contactor coil, TCC switch, HP switch). Looking at
// raw pin level can't reliably distinguish "AC present, between pulses"
// from "AC absent"/"wiring fault", so presence is decided by counting edges
// within a rolling time window instead.
//
// DigitalInputMonitor below is the real windowed-detection logic, written
// for real now (pure, no Arduino deps) because it's fully unit-testable.
// Only the edge *source* is stubbed for M0: DigitalInputHal::tickStub()
// synthesizes plausible edges. The M1 replacement wires a real GPIO ISR
// that calls DigitalInputMonitor::recordEdge() directly; the detection
// logic itself does not change.
#pragma once

#include <cstddef>
#include <cstdint>

#include "i_sensor.h"

constexpr size_t kDigitalInputChannelCount = 4;

enum class DigitalInputChannel : uint8_t {
    Beater = 0,
    Contactor = 1,
    Tcc = 2,
    Hp = 3,
};

class DigitalInputMonitor {
public:
    // Rolling window length used to decide "active".
    static constexpr uint32_t kWindowMs = 100;
    // Minimum edges observed within the window to call a channel active.
    static constexpr uint8_t kActiveEdgeThreshold = 2;
    // Per-channel edge history depth. Sized generously relative to expected
    // mains-derived pulse rates so the window is never edge-starved.
    static constexpr size_t kMaxEdgesTracked = 32;

    DigitalInputMonitor() = default;

    // Records one edge on `ch` observed at `now_ms` (millis()-style,
    // monotonically increasing, wraparound-safe). Called from the GPIO ISR
    // (real M1 impl) or the stub's synthetic pulse generator.
    void recordEdge(DigitalInputChannel ch, uint32_t now_ms);

    // True if `ch` has seen >= kActiveEdgeThreshold edges within the last
    // kWindowMs ms, evaluated as of `now_ms`.
    bool isActive(DigitalInputChannel ch, uint32_t now_ms) const;

    // Number of edges retained for `ch` that fall within the window ending
    // at `now_ms`. Exposed mainly for unit tests.
    uint8_t edgeCountInWindow(DigitalInputChannel ch, uint32_t now_ms) const;

private:
    struct ChannelState {
        uint32_t edgeTimes[kMaxEdgesTracked] = {0};
        size_t writeIdx = 0;
        size_t count = 0; // valid entries in edgeTimes, <= kMaxEdgesTracked
    };

    ChannelState channels_[kDigitalInputChannelCount];

    ChannelState& stateFor(DigitalInputChannel ch);
    const ChannelState& stateFor(DigitalInputChannel ch) const;
};

// STUB(M1): real replacement is a GPIO-ISR-driven edge source wired to
// pins::ACSENSE_BEATER/CONTACTOR/TCC/HP; the windowed detection above is
// reused unchanged.
class DigitalInputHal : public ISensor {
public:
    DigitalInputHal();

    bool begin() override;
    bool healthy() const override;
    const char* name() const override;

    // Advances the stub edge simulation and the underlying detector to
    // `now_ms`. Call frequently from the sampling path in place of a real
    // GPIO ISR. `now_ms` should be a monotonically increasing millis()-style
    // clock.
    void tickStub(uint32_t now_ms);

    // Windowed AC-presence result as of the most recent tickStub() call.
    bool isActive(DigitalInputChannel ch) const;

private:
    DigitalInputMonitor monitor_;
    uint32_t nextEdgeDueMs_[kDigitalInputChannelCount] = {0};
    uint32_t lastNowMs_ = 0;
    bool healthy_ = false;
};
