#include "record_format.h"

#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>

namespace record_format {

namespace {

// Appends a float field followed by ',' (or not, caller decides). NaN/inf
// become an empty field per the format spec ("missing/NaN -> empty field").
void appendFloatField(std::string& out, float v) {
    if (std::isnan(v) || std::isinf(v)) {
        return; // empty field
    }
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%.3f", static_cast<double>(v));
    out += buf;
}

void appendBoolField(std::string& out, bool v) {
    out += v ? '1' : '0';
}

} // namespace

std::string formatIso8601(uint64_t ts_unix_ms) {
    const time_t seconds = static_cast<time_t>(ts_unix_ms / 1000);
    std::tm tm_utc{};
#if defined(_WIN32)
    gmtime_s(&tm_utc, &seconds);
#else
    gmtime_r(&seconds, &tm_utc);
#endif
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02dZ",
                  tm_utc.tm_year + 1900, tm_utc.tm_mon + 1, tm_utc.tm_mday,
                  tm_utc.tm_hour, tm_utc.tm_min, tm_utc.tm_sec);
    return std::string(buf);
}

std::string channelsCsvHeader() {
    return "ts_iso,ts_unix_ms,current_beater_a,current_compressor_a,"
           "temp_cylinder_c,temp_cond_in_c,temp_cond_out_c,temp_ambient_c,"
           "temp_hopper_c,temp_discharge_c,beater_on,compressor_cmd,"
           "tcc_satisfied,hp_ok";
}

std::string formatChannelRowCsv(const ChannelRow& row) {
    std::string out;
    out.reserve(160);

    out += formatIso8601(row.ts_unix_ms);
    out += ',';
    out += std::to_string(row.ts_unix_ms);
    out += ',';
    appendFloatField(out, row.current_beater_a);
    out += ',';
    appendFloatField(out, row.current_compressor_a);
    out += ',';
    appendFloatField(out, row.temp_cylinder_c);
    out += ',';
    appendFloatField(out, row.temp_cond_in_c);
    out += ',';
    appendFloatField(out, row.temp_cond_out_c);
    out += ',';
    appendFloatField(out, row.temp_ambient_c);
    out += ',';
    appendFloatField(out, row.temp_hopper_c);
    out += ',';
    appendFloatField(out, row.temp_discharge_c);
    out += ',';
    appendBoolField(out, row.beater_on);
    out += ',';
    appendBoolField(out, row.compressor_cmd);
    out += ',';
    appendBoolField(out, row.tcc_satisfied);
    out += ',';
    appendBoolField(out, row.hp_ok);

    return out;
}

std::string vibSummaryCsvHeader() {
    return "ts_iso,ts_unix_ms,pod_id,rms_x_g,rms_y_g,rms_z_g,peak_x_g,"
           "peak_y_g,peak_z_g,band_low_g2,band_mid_g2,band_high_g2";
}

std::string formatVibSummaryCsv(const VibSummary& v) {
    std::string out;
    out.reserve(160);

    out += formatIso8601(v.ts_unix_ms);
    out += ',';
    out += std::to_string(v.ts_unix_ms);
    out += ',';
    out += std::to_string(static_cast<unsigned>(v.pod_id));
    out += ',';
    appendFloatField(out, v.rms_x_g);
    out += ',';
    appendFloatField(out, v.rms_y_g);
    out += ',';
    appendFloatField(out, v.rms_z_g);
    out += ',';
    appendFloatField(out, v.peak_x_g);
    out += ',';
    appendFloatField(out, v.peak_y_g);
    out += ',';
    appendFloatField(out, v.peak_z_g);
    out += ',';
    appendFloatField(out, v.band_low_g2);
    out += ',';
    appendFloatField(out, v.band_mid_g2);
    out += ',';
    appendFloatField(out, v.band_high_g2);

    return out;
}

std::string formatEventJsonl(uint64_t ts_unix_ms, const char* type, const char* detail_json) {
    std::string out;
    out.reserve(128);
    out += "{\"ts_iso\":\"";
    out += formatIso8601(ts_unix_ms);
    out += "\",\"ts_unix_ms\":";
    out += std::to_string(ts_unix_ms);
    out += ",\"type\":\"";
    out += type;
    out += "\",\"detail\":";
    out += (detail_json != nullptr && detail_json[0] != '\0') ? detail_json : "{}";
    out += "}";
    return out;
}

namespace {

void putU16LE(uint8_t* out, uint16_t v) {
    out[0] = static_cast<uint8_t>(v & 0xFF);
    out[1] = static_cast<uint8_t>((v >> 8) & 0xFF);
}

void putU32LE(uint8_t* out, uint32_t v) {
    out[0] = static_cast<uint8_t>(v & 0xFF);
    out[1] = static_cast<uint8_t>((v >> 8) & 0xFF);
    out[2] = static_cast<uint8_t>((v >> 16) & 0xFF);
    out[3] = static_cast<uint8_t>((v >> 24) & 0xFF);
}

void putU64LE(uint8_t* out, uint64_t v) {
    for (int i = 0; i < 8; ++i) {
        out[i] = static_cast<uint8_t>((v >> (8 * i)) & 0xFF);
    }
}

} // namespace

void writeVibBurstHeader(uint8_t out[32],
                          uint8_t pod_id,
                          uint32_t sample_rate_hz,
                          uint32_t n_samples,
                          uint64_t start_ts_unix_ms,
                          float scale_g_per_lsb) {
    std::memset(out, 0, 32);

    out[0] = 'F';
    out[1] = 'V';
    out[2] = 'B';
    out[3] = '1';
    out[4] = 1; // version
    out[5] = pod_id;
    putU16LE(&out[6], 0); // reserved
    putU32LE(&out[8], sample_rate_hz);
    putU32LE(&out[12], n_samples);
    out[16] = 3; // n_axes
    out[17] = 0;
    out[18] = 0;
    out[19] = 0;
    putU64LE(&out[20], start_ts_unix_ms);

    uint32_t scale_bits;
    std::memcpy(&scale_bits, &scale_g_per_lsb, sizeof(scale_bits));
    putU32LE(&out[28], scale_bits);
}

} // namespace record_format
