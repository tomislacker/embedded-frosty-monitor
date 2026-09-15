// cloud_aggregate.h - pure aggregation logic for CloudSink's publish
// payloads. Deliberately Arduino-free (same pattern as record_format.h) so
// it compiles and is unit tested in the native PlatformIO environment; the
// Arduino/WiFi/MQTT-specific parts of cloud publishing live in
// storage/cloud_sink.{h,cpp} instead, which this module knows nothing about.
//
// See docs/firmware/connectivity.md for the publish policy this backs
// (aggregate channels/vibration over a window, publish events immediately)
// and the exact JSON schema toJson() produces.
#pragma once

#include <cstdint>
#include <string>

#include "record_types.h"

namespace cloud_aggregate {

// Running mean/min/max for one numeric channel across a publish window.
// NaN/inf samples are excluded from the accumulation entirely (matching the
// "missing sensor" convention used throughout the on-card format) rather
// than poisoning the aggregate -- a channel with zero non-NaN samples in the
// window has hasData() == false and is omitted from the published JSON.
struct NumericAgg {
    double sum = 0.0;
    float min = 0.0f;
    float max = 0.0f;
    uint32_t count = 0;

    void accumulate(float v);
    bool hasData() const { return count > 0; }
    float mean() const { return hasData() ? static_cast<float>(sum / count) : 0.0f; }
};

// Aggregates ChannelRow records (the 1Hz channel stream) over a publish
// window: mean/min/max per numeric channel, last-value semantics for the
// four boolean state channels (the most recent sample in the window wins --
// this is "current state", not something meaningful to average).
class ChannelAggregator {
public:
    void reset();
    void add(const ChannelRow& row);
    uint32_t count() const { return n_; }
    uint64_t lastTsMs() const { return lastTsMs_; }

    // Serializes the current accumulator as one JSON object (see
    // docs/firmware/connectivity.md for the schema). ts_unix_ms/ts_iso in
    // the payload are the window's END timestamp (the last row folded in),
    // not the window start. `window_s` is echoed from CloudConfig by the
    // caller -- this module has no notion of wall-clock time itself.
    std::string toJson(uint32_t window_s) const;

private:
    uint32_t n_ = 0;
    uint64_t lastTsMs_ = 0;
    NumericAgg current_beater_a_;
    NumericAgg current_compressor_a_;
    NumericAgg temp_cylinder_c_;
    NumericAgg temp_cond_in_c_;
    NumericAgg temp_cond_out_c_;
    NumericAgg temp_ambient_c_;
    NumericAgg temp_hopper_c_;
    NumericAgg temp_discharge_c_;
    NumericAgg drip_rate_cpm_;
    NumericAgg moisture_raw_;
    NumericAgg refrigerant_raw_;
    bool beater_on_ = false;
    bool compressor_cmd_ = false;
    bool tcc_satisfied_ = false;
    bool hp_ok_ = false;
};

// Aggregates VibSummary records for a single pod over a publish window.
// CloudSink keeps one instance per pod (beater, compressor) since pod_id is
// part of the aggregate's identity, not a channel within it.
class VibAggregator {
public:
    void reset();
    void add(const VibSummary& v);
    uint32_t count() const { return n_; }
    uint64_t lastTsMs() const { return lastTsMs_; }

    std::string toJson(uint32_t window_s) const;

private:
    uint32_t n_ = 0;
    uint64_t lastTsMs_ = 0;
    uint8_t podId_ = 0;
    NumericAgg rms_x_g_;
    NumericAgg rms_y_g_;
    NumericAgg rms_z_g_;
    NumericAgg peak_x_g_;
    NumericAgg peak_y_g_;
    NumericAgg peak_z_g_;
    NumericAgg band_low_g2_;
    NumericAgg band_mid_g2_;
    NumericAgg band_high_g2_;
};

} // namespace cloud_aggregate
