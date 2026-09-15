#include "temp_ds18b20.h"

#include <Arduino.h>
#include <cmath>

bool TempDs18b20::begin() {
    healthy_ = true;
    return true;
}

bool TempDs18b20::healthy() const {
    return healthy_;
}

const char* TempDs18b20::name() const {
    return "temp_ds18b20(stub)";
}

float TempDs18b20::readC(Channel ch) {
    if (ch == Channel::Hopper) {
        return NAN; // STUB models an unpopulated hopper probe
    }

    const float t = millis() / 1000.0f;
    const float noise = (static_cast<float>(random(-50, 51)) / 100.0f) * 0.1f;

    switch (ch) {
        case Channel::Cylinder:
            return 4.0f + 1.5f * sinf(t * 0.02f) + noise;
        case Channel::CondIn:
            return 32.0f + 3.0f * sinf(t * 0.015f + 0.5f) + noise;
        case Channel::CondOut:
            return 24.0f + 2.5f * sinf(t * 0.015f + 1.1f) + noise;
        case Channel::Ambient:
            return 21.0f + 1.0f * sinf(t * 0.01f) + noise;
        default:
            return NAN;
    }
}
