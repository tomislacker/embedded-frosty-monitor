#include "temp_thermocouple_max31855.h"

#include <Arduino.h>
#include <cmath>

bool ThermocoupleMax31855::begin() {
    healthy_ = true;
    return true;
}

bool ThermocoupleMax31855::healthy() const {
    return healthy_;
}

const char* ThermocoupleMax31855::name() const {
    return "temp_thermocouple_max31855(stub)";
}

float ThermocoupleMax31855::readDischargeC(bool compressorOn) {
    const float t = millis() / 1000.0f;
    const float noise = (static_cast<float>(random(-100, 101)) / 100.0f) * 0.3f;

    if (compressorOn) {
        return 85.0f + 8.0f * sinf(t * 0.05f) + noise;
    }
    return 25.0f + 2.0f * sinf(t * 0.02f) + noise;
}
