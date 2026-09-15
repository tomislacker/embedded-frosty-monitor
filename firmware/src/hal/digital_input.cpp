#include "digital_input.h"

namespace {

// Simulated pulse period per channel while "AC present" in the stub. Real
// mains-derived opto pulses arrive much faster than this; these values just
// need to comfortably clear kActiveEdgeThreshold within kWindowMs.
constexpr uint32_t kStubPulsePeriodMs[kDigitalInputChannelCount] = {
    20, // Beater: on most of the time in the fake duty cycle
    35, // Contactor
    40, // Tcc
    50, // Hp
};

// Fake "is this circuit energized right now" duty cycle, driven purely off
// now_ms so the stub is deterministic and testable.
bool stubChannelEnergized(DigitalInputChannel ch, uint32_t now_ms) {
    switch (ch) {
        case DigitalInputChannel::Beater:
            // Beater runs most of the time, brief periodic pauses.
            return (now_ms % 4000) < 3400;
        case DigitalInputChannel::Contactor:
            // Compressor contactor cycles roughly 30s on / 30s off.
            return (now_ms % 60000) < 30000;
        case DigitalInputChannel::Tcc:
            // TCC (temperature control cutout) satisfied most of the time.
            return (now_ms % 20000) < 17000;
        case DigitalInputChannel::Hp:
            // HP (high pressure) switch ok almost always.
            return (now_ms % 30000) < 29000;
    }
    return false;
}

} // namespace

// ---- DigitalInputMonitor: real windowed-detection logic ----

DigitalInputMonitor::ChannelState& DigitalInputMonitor::stateFor(DigitalInputChannel ch) {
    return channels_[static_cast<size_t>(ch)];
}

const DigitalInputMonitor::ChannelState& DigitalInputMonitor::stateFor(DigitalInputChannel ch) const {
    return channels_[static_cast<size_t>(ch)];
}

void DigitalInputMonitor::recordEdge(DigitalInputChannel ch, uint32_t now_ms) {
    ChannelState& s = stateFor(ch);
    s.edgeTimes[s.writeIdx] = now_ms;
    s.writeIdx = (s.writeIdx + 1) % kMaxEdgesTracked;
    if (s.count < kMaxEdgesTracked) {
        ++s.count;
    }
}

uint8_t DigitalInputMonitor::edgeCountInWindow(DigitalInputChannel ch, uint32_t now_ms) const {
    const ChannelState& s = stateFor(ch);
    uint8_t inWindow = 0;
    for (size_t i = 0; i < s.count; ++i) {
        // Unsigned subtraction wraps correctly across millis() rollover as
        // long as the edge is not more than ~2^31 ms in the past, which is
        // always true here since we only ever look back kWindowMs.
        const uint32_t age = now_ms - s.edgeTimes[i];
        if (age <= kWindowMs) {
            ++inWindow;
        }
    }
    return inWindow;
}

bool DigitalInputMonitor::isActive(DigitalInputChannel ch, uint32_t now_ms) const {
    return edgeCountInWindow(ch, now_ms) >= kActiveEdgeThreshold;
}

// ---- DigitalInputHal: STUB(M1) synthetic edge source ----

DigitalInputHal::DigitalInputHal() = default;

bool DigitalInputHal::begin() {
    healthy_ = true;
    return true;
}

bool DigitalInputHal::healthy() const {
    return healthy_;
}

const char* DigitalInputHal::name() const {
    return "digital_input(stub)";
}

void DigitalInputHal::tickStub(uint32_t now_ms) {
    lastNowMs_ = now_ms;
    for (size_t i = 0; i < kDigitalInputChannelCount; ++i) {
        const auto ch = static_cast<DigitalInputChannel>(i);
        if (!stubChannelEnergized(ch, now_ms)) {
            continue;
        }
        if (now_ms >= nextEdgeDueMs_[i]) {
            monitor_.recordEdge(ch, now_ms);
            nextEdgeDueMs_[i] = now_ms + kStubPulsePeriodMs[i];
        }
    }
}

bool DigitalInputHal::isActive(DigitalInputChannel ch) const {
    return monitor_.isActive(ch, lastNowMs_);
}
