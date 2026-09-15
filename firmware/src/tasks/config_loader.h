// config_loader.h - reads /config.json from SD, applies defaults if
// absent/invalid, writes manifest.json, and services a tiny serial CLI
// (SETTIME <iso8601>, STATUS) used at bench bring-up before a proper UI
// exists.
#pragma once

#include <cstdint>
#include <string>

#include "../hal/i_storage_sink.h"
#include "../hal/rtc_ds3231.h"
#include "../storage/cloud_config.h"

struct AppConfig {
    std::string deployment_id = "unassigned";
    std::string machine_model = "unknown";
    std::string machine_serial = "unknown";
    std::string technician = "unknown";

    // Vibration capture cadence. Spec default is 300s in the field; dev/stub
    // builds (FROSTY_DEV_MODE) default to 15s so the pipeline is visibly
    // exercised on the bench without waiting 5 minutes.
    uint32_t vib_capture_interval_s = 300;
    uint32_t vib_burst_duration_s = 2;
    uint32_t vib_sample_rate_hz = 400;

    // Sampling scheduler current-spike threshold (amps above the stub's
    // steady-state wander) that triggers an out-of-cycle vibration burst.
    float current_spike_threshold_a = 5.0f;

    // Premium-tier real-time remote monitoring. Disabled unless config.json
    // has a "cloud" object with "enabled":true -- see cloud_config.h and
    // docs/firmware/connectivity.md.
    CloudConfig cloud;
};

class ConfigLoader {
public:
    explicit ConfigLoader(IStorageSink* sink);

    // Reads /config.json from SD (direct SD.h access, not through
    // IStorageSink -- config.json is a one-shot whole-file read/write, not
    // part of the per-record append stream that sink models). Falls back to
    // AppConfig{} defaults if the card is absent or the file is
    // missing/invalid. Always succeeds (never blocks pipeline startup).
    void loadOrDefault();

    // Writes manifest.json (schema_version 1) populated from the effective
    // config + firmware version + start timestamp. No-op if the card isn't
    // ready.
    void writeManifest(RtcDs3231& rtc);

    const AppConfig& config() const { return config_; }

    // Reads any pending line from Serial and handles SETTIME <iso8601> /
    // STATUS. Call frequently (non-blocking) from a task loop.
    void pollSerialCli(RtcDs3231& rtc);

private:
    IStorageSink* sink_;
    AppConfig config_;
    std::string startTsIso_;
    std::string lineBuf_;

    void handleCliLine(const std::string& line, RtcDs3231& rtc);
};
