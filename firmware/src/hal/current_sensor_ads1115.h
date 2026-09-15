// current_sensor_ads1115.h - AC current sensing via ADS1115 ADC reading
// current-transformer front ends.
//
// STUB(M1): real replacement reads the ADS1115 over I2C (addr
// i2c_addr::ADS1115) via Adafruit_ADS1X15 (or equivalent), converts raw
// counts to RMS amps using the CT burden-resistor scale factor, and drives
// begin()/healthy() off actual I2C bus responses.
#pragma once

#include <cstdint>

#include "i_sensor.h"

class CurrentSensorAds1115 : public ISensor {
public:
    enum class Channel : uint8_t {
        Beater = 0,
        Compressor = 1,
    };

    CurrentSensorAds1115() = default;

    bool begin() override;
    bool healthy() const override;
    const char* name() const override;

    // Plausible fake RMS current reading in amps for `ch`:
    //   Beater: wanders ~2-4A continuously.
    //   Compressor: fake duty cycle, ~0A off / ~6-8A on.
    float readRmsAmps(Channel ch);

private:
    bool healthy_ = false;
};
