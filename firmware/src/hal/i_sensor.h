// i_sensor.h - minimal common interface implemented by every HAL driver
// (stub or real). Kept tiny on purpose: sensor-specific read methods live
// on the concrete classes, this just standardizes lifecycle + health.
#pragma once

class ISensor {
public:
    virtual ~ISensor() = default;

    // Initialize the underlying peripheral/bus. Returns true on success.
    // Stub implementations always return true (no hardware to fail on).
    virtual bool begin() = 0;

    // Returns true if the sensor is currently believed to be producing
    // valid data (e.g. bus responded, last read wasn't stale/error).
    virtual bool healthy() const = 0;

    // Short human-readable name, used in logs/manifest/error events.
    virtual const char* name() const = 0;
};
