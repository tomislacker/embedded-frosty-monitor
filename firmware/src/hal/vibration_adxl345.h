// vibration_adxl345.h - triaxial vibration pods (ADXL345 accelerometers).
//
// STUB(M1): real replacement reads the ADXL345 FIFO over I2C (addr
// i2c_addr::ADXL345_POD_A / _POD_B) at the requested output data rate via
// Adafruit_ADXL345_U (or a raw register driver for FIFO burst reads), and
// fills the same interleaved XYZ int16 buffer this stub does. begin()
// would probe the DEVID register; healthy() would track I2C ack/FIFO
// overrun state.
#pragma once

#include <cstdint>

#include "i_sensor.h"

class VibrationAdxl345 : public ISensor {
public:
    VibrationAdxl345(uint8_t podId, uint8_t i2cAddr);

    bool begin() override;
    bool healthy() const override;
    const char* name() const override;

    uint8_t podId() const { return podId_; }

    // ADXL345 full-resolution scale factor, ~3.9 mg/LSB, used to convert
    // raw int16 counts to g when needed (also written into the .bin header).
    float scaleGPerLsb() const { return 0.0039f; }

    // Fills `xyz_interleaved` (length n_samples * 3) with synthesized
    // sine + noise data resembling a running motor/pod at `sample_rate_hz`.
    void fillBurst(int16_t* xyz_interleaved, uint32_t n_samples, uint32_t sample_rate_hz);

private:
    uint8_t podId_;
    uint8_t i2cAddr_;
    bool healthy_ = false;
    char nameBuf_[24];
};
