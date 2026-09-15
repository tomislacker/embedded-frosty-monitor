// temp_thermocouple_max31855.h - discharge-line thermocouple amplifier.
//
// STUB(M1): real replacement reads the MAX31855 over SPI (CS =
// pins::MAX31855_CS, shared bus with the SD card -- see the SPI mutex note
// in tasks/storage_writer.h) and decodes its 32-bit frame, surfacing fault
// bits (open circuit / short to Vcc / short to GND) through healthy().
#pragma once

#include "i_sensor.h"

class ThermocoupleMax31855 : public ISensor {
public:
    ThermocoupleMax31855() = default;

    bool begin() override;
    bool healthy() const override;
    const char* name() const override;

    // Plausible discharge-line temperature in Celsius: wanders in the
    // 75-95C band while `compressorOn` is true, otherwise relaxes toward
    // ambient.
    float readDischargeC(bool compressorOn);

private:
    bool healthy_ = false;
};
