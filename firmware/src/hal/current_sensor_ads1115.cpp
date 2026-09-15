#include "current_sensor_ads1115.h"

#include <Arduino.h>
#include <cmath>

bool CurrentSensorAds1115::begin() {
    healthy_ = true;
    return true;
}

bool CurrentSensorAds1115::healthy() const {
    return healthy_;
}

const char* CurrentSensorAds1115::name() const {
    return "current_sensor_ads1115(stub)";
}

float CurrentSensorAds1115::readRmsAmps(Channel ch) {
    const float t = millis() / 1000.0f;
    const float noise = (static_cast<float>(random(-100, 101)) / 100.0f) * 0.15f;

    switch (ch) {
        case Channel::Beater: {
            // Wanders ~2-4A continuously.
            const float wander = 1.0f * sinf(t * 0.21f) + 1.0f * sinf(t * 0.07f + 1.3f);
            return 3.0f + wander * 0.5f + noise;
        }
        case Channel::Compressor: {
            // Fake ~50s on / 40s off duty cycle: 0A off, ~6-8A on.
            const uint32_t phase = static_cast<uint32_t>(millis()) % 90000u;
            const bool on = phase < 50000u;
            if (!on) {
                return fabsf(noise) * 0.05f; // near-zero, tiny noise floor
            }
            const float wander = sinf(t * 0.35f) * 0.6f;
            return 7.0f + wander + noise;
        }
    }
    return 0.0f;
}
