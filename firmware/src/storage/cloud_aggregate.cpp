#include "cloud_aggregate.h"

#include <cmath>
#include <cstdio>

#include "record_format.h"

namespace cloud_aggregate {

namespace {

void appendFloat(std::string& out, float v) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%.3f", static_cast<double>(v));
    out += buf;
}

void appendBool(std::string& out, bool v) {
    out += v ? "true" : "false";
}

// Appends `"key":{"mean":..,"min":..,"max":..},` -- including the trailing
// comma -- or nothing at all if the channel had no non-NaN samples this
// window. Every call site relies on a field that's always present (n, or
// the bool block) following immediately after, so the dangling-vs-no
// trailing comma is never an issue either way.
void appendNumericField(std::string& out, const char* key, const NumericAgg& agg) {
    if (!agg.hasData()) {
        return;
    }
    out += '"';
    out += key;
    out += "\":{\"mean\":";
    appendFloat(out, agg.mean());
    out += ",\"min\":";
    appendFloat(out, agg.min);
    out += ",\"max\":";
    appendFloat(out, agg.max);
    out += "},";
}

} // namespace

void NumericAgg::accumulate(float v) {
    if (std::isnan(v) || std::isinf(v)) {
        return; // excluded -- see hasData()/the struct comment in the header
    }
    if (count == 0) {
        min = v;
        max = v;
    } else {
        if (v < min) min = v;
        if (v > max) max = v;
    }
    sum += v;
    ++count;
}

void ChannelAggregator::reset() {
    *this = ChannelAggregator();
}

void ChannelAggregator::add(const ChannelRow& row) {
    ++n_;
    lastTsMs_ = row.ts_unix_ms;
    current_beater_a_.accumulate(row.current_beater_a);
    current_compressor_a_.accumulate(row.current_compressor_a);
    temp_cylinder_c_.accumulate(row.temp_cylinder_c);
    temp_cond_in_c_.accumulate(row.temp_cond_in_c);
    temp_cond_out_c_.accumulate(row.temp_cond_out_c);
    temp_ambient_c_.accumulate(row.temp_ambient_c);
    temp_hopper_c_.accumulate(row.temp_hopper_c);
    temp_discharge_c_.accumulate(row.temp_discharge_c);
    drip_rate_cpm_.accumulate(row.drip_rate_cpm);
    moisture_raw_.accumulate(row.moisture_raw);
    refrigerant_raw_.accumulate(row.refrigerant_raw);
    // Last-value semantics: booleans describe current state, not something
    // meaningful to average over a window.
    beater_on_ = row.beater_on;
    compressor_cmd_ = row.compressor_cmd;
    tcc_satisfied_ = row.tcc_satisfied;
    hp_ok_ = row.hp_ok;
}

std::string ChannelAggregator::toJson(uint32_t window_s) const {
    std::string out;
    out.reserve(512);

    out += "{\"ts_iso\":\"";
    out += record_format::formatIso8601(lastTsMs_);
    out += "\",\"ts_unix_ms\":";
    out += std::to_string(lastTsMs_);
    out += ",\"window_s\":";
    out += std::to_string(window_s);
    out += ",\"n\":";
    out += std::to_string(n_);
    out += ",";

    appendNumericField(out, "current_beater_a", current_beater_a_);
    appendNumericField(out, "current_compressor_a", current_compressor_a_);
    appendNumericField(out, "temp_cylinder_c", temp_cylinder_c_);
    appendNumericField(out, "temp_cond_in_c", temp_cond_in_c_);
    appendNumericField(out, "temp_cond_out_c", temp_cond_out_c_);
    appendNumericField(out, "temp_ambient_c", temp_ambient_c_);
    appendNumericField(out, "temp_hopper_c", temp_hopper_c_);
    appendNumericField(out, "temp_discharge_c", temp_discharge_c_);
    appendNumericField(out, "drip_rate_cpm", drip_rate_cpm_);
    appendNumericField(out, "moisture_raw", moisture_raw_);
    appendNumericField(out, "refrigerant_raw", refrigerant_raw_);

    out += "\"beater_on\":";
    appendBool(out, beater_on_);
    out += ",\"compressor_cmd\":";
    appendBool(out, compressor_cmd_);
    out += ",\"tcc_satisfied\":";
    appendBool(out, tcc_satisfied_);
    out += ",\"hp_ok\":";
    appendBool(out, hp_ok_);
    out += "}";

    return out;
}

void VibAggregator::reset() {
    *this = VibAggregator();
}

void VibAggregator::add(const VibSummary& v) {
    ++n_;
    lastTsMs_ = v.ts_unix_ms;
    podId_ = v.pod_id;
    rms_x_g_.accumulate(v.rms_x_g);
    rms_y_g_.accumulate(v.rms_y_g);
    rms_z_g_.accumulate(v.rms_z_g);
    peak_x_g_.accumulate(v.peak_x_g);
    peak_y_g_.accumulate(v.peak_y_g);
    peak_z_g_.accumulate(v.peak_z_g);
    band_low_g2_.accumulate(v.band_low_g2);
    band_mid_g2_.accumulate(v.band_mid_g2);
    band_high_g2_.accumulate(v.band_high_g2);
}

std::string VibAggregator::toJson(uint32_t window_s) const {
    std::string out;
    out.reserve(512);

    out += "{\"ts_iso\":\"";
    out += record_format::formatIso8601(lastTsMs_);
    out += "\",\"ts_unix_ms\":";
    out += std::to_string(lastTsMs_);
    out += ",\"window_s\":";
    out += std::to_string(window_s);
    out += ",\"n\":";
    out += std::to_string(n_);
    out += ",\"pod_id\":";
    out += std::to_string(static_cast<unsigned>(podId_));
    out += ",";

    appendNumericField(out, "rms_x_g", rms_x_g_);
    appendNumericField(out, "rms_y_g", rms_y_g_);
    appendNumericField(out, "rms_z_g", rms_z_g_);
    appendNumericField(out, "peak_x_g", peak_x_g_);
    appendNumericField(out, "peak_y_g", peak_y_g_);
    appendNumericField(out, "peak_z_g", peak_z_g_);
    appendNumericField(out, "band_low_g2", band_low_g2_);
    appendNumericField(out, "band_mid_g2", band_mid_g2_);
    // Last field: appendNumericField() always adds its own trailing comma,
    // so strip the one after band_high_g2 before closing the object.
    appendNumericField(out, "band_high_g2", band_high_g2_);
    if (!out.empty() && out.back() == ',') {
        out.pop_back();
    }
    out += "}";

    return out;
}

} // namespace cloud_aggregate
