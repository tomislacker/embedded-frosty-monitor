#include "vibration_adxl345.h"

#include <Arduino.h>
#include <cmath>
#include <cstdio>

VibrationAdxl345::VibrationAdxl345(uint8_t podId, uint8_t i2cAddr)
    : podId_(podId), i2cAddr_(i2cAddr) {
    std::snprintf(nameBuf_, sizeof(nameBuf_), "vibration_pod_%u(stub)", podId_);
}

bool VibrationAdxl345::begin() {
    healthy_ = true;
    return true;
}

bool VibrationAdxl345::healthy() const {
    return healthy_;
}

const char* VibrationAdxl345::name() const {
    return nameBuf_;
}

void VibrationAdxl345::fillBurst(int16_t* xyz_interleaved, uint32_t n_samples, uint32_t sample_rate_hz) {
    if (xyz_interleaved == nullptr || n_samples == 0 || sample_rate_hz == 0) {
        return;
    }

    // Pod A (beater) gets a faster/rougher synthetic signal, pod B
    // (compressor) a slower/smoother one, just to make the two pods look
    // visibly distinct in the stub data.
    const float baseFreqHz = (podId_ == 1) ? 42.0f : 29.0f;
    const float baseAmpG = (podId_ == 1) ? 0.35f : 0.18f;
    const float dt = 1.0f / static_cast<float>(sample_rate_hz);
    const int16_t fullScale = 256; // counts per g at scaleGPerLsb() ~ 1/0.0039

    for (uint32_t i = 0; i < n_samples; ++i) {
        const float t = static_cast<float>(i) * dt;
        for (uint8_t axis = 0; axis < 3; ++axis) {
            const float axisPhase = axis * 2.0944f; // 120 degrees apart
            const float noise = (static_cast<float>(random(-100, 101)) / 100.0f) * 0.05f;
            const float g = baseAmpG * sinf(2.0f * static_cast<float>(M_PI) * baseFreqHz * t + axisPhase) + noise;
            int32_t counts = static_cast<int32_t>(g * fullScale);
            if (counts > INT16_MAX) counts = INT16_MAX;
            if (counts < INT16_MIN) counts = INT16_MIN;
            xyz_interleaved[i * 3 + axis] = static_cast<int16_t>(counts);
        }
    }
}
