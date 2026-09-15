// temp_ds18b20.h - 1-Wire temperature probes (cylinder, condenser in/out,
// ambient, hopper).
//
// STUB(M1): real replacement enumerates DS18B20 addresses on the 1-Wire bus
// at pins::ONEWIRE_BUS (via OneWire + DallasTemperature), maps each address
// to a Channel per config.json's channel_map, and issues convert/read
// commands. begin() would fail (return false) if fewer than the expected
// number of devices are found; healthy() would track per-channel CRC/
// timeout errors. The hopper probe is optional hardware on some deployments
// -- NAN is the correct "absent" representation both in the stub and later.
#pragma once

#include <cstdint>

#include "i_sensor.h"

class TempDs18b20 : public ISensor {
public:
    enum class Channel : uint8_t {
        Cylinder = 0,
        CondIn = 1,
        CondOut = 2,
        Ambient = 3,
        Hopper = 4, // often absent; stub always returns NAN
        Count = 5,
    };

    TempDs18b20() = default;

    bool begin() override;
    bool healthy() const override;
    const char* name() const override;

    // Slow-moving plausible temperature in Celsius for `ch`. Returns NAN
    // for Hopper to model an unpopulated probe.
    float readC(Channel ch);

private:
    bool healthy_ = false;
};
