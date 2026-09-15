// rtc_ds3231.h - battery-backed real-time clock.
//
// STUB(M1): real replacement reads/writes the DS3231 over I2C (addr
// i2c_addr::DS3231) via RTClib (or a raw register driver) and uses it to
// discipline the system clock at boot (and periodically, to correct ESP32
// crystal drift). For M0 this simply wraps the libc time()/settimeofday()
// system clock, which is perfectly adequate for exercising the pipeline
// without hardware: begin() seeds a sane default time if none has been set
// (settimeofday is never called by ESP32 Arduino core on its own), and
// setTime() is exactly what the ConfigLoader `SETTIME` serial CLI command
// calls either way.
#pragma once

#include <cstdint>

#include "i_sensor.h"

class RtcDs3231 : public ISensor {
public:
    RtcDs3231() = default;

    bool begin() override;
    bool healthy() const override;
    const char* name() const override;

    // Current time as milliseconds since Unix epoch (UTC).
    uint64_t now_ms() const;

    // Parses a UTC ISO-8601 timestamp ("YYYY-MM-DDTHH:MM:SSZ") and applies
    // it via settimeofday(). Returns false on parse failure (clock is left
    // unchanged).
    bool setTime(const char* iso8601);

private:
    bool healthy_ = false;
};
