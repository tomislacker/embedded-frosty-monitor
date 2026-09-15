// record_format.h - pure formatting functions for the on-disk data format
// (see docs/data-format spec, format v1). No Arduino headers are included
// here so this file (and its .cpp) can be compiled and unit tested in the
// native PlatformIO environment as well as on-target.
#pragma once

#include <cstdint>
#include <cstddef>
#include <string>

#include "record_types.h"

namespace record_format {

// Formats a unix-ms timestamp as UTC ISO-8601, e.g. "2026-09-14T12:34:56Z".
std::string formatIso8601(uint64_t ts_unix_ms);

// Exact channels_YYYYMMDD.csv header line (no trailing newline).
std::string channelsCsvHeader();

// One channels CSV row (no trailing newline). NaN floats are emitted as
// empty fields per the format spec.
std::string formatChannelRowCsv(const ChannelRow& row);

// Exact vibration/vib_summary_YYYYMMDD.csv header line (no trailing newline).
std::string vibSummaryCsvHeader();

// One vib summary CSV row (no trailing newline).
std::string formatVibSummaryCsv(const VibSummary& v);

// One events_YYYYMMDD.jsonl line (no trailing newline). `detail_json` must
// already be a valid JSON object literal, e.g. "{\"button\":\"journal\"}".
std::string formatEventJsonl(uint64_t ts_unix_ms, const char* type, const char* detail_json);

// Packs the 32-byte little-endian vib_<pod>_<ts>.bin header into `out`.
// Layout:
//   0  : magic "FVB1" (4 bytes, no NUL terminator)
//   4  : u8  version (=1)
//   5  : u8  pod_id (1=beater, 2=compressor)
//   6  : u16 reserved (=0)
//   8  : u32 sample_rate_hz
//   12 : u32 n_samples (per axis)
//   16 : u8  n_axes (=3)
//   17 : u8[3] reserved (=0)
//   20 : u64 start_ts_unix_ms
//   28 : f32 scale_g_per_lsb
void writeVibBurstHeader(uint8_t out[32],
                          uint8_t pod_id,
                          uint32_t sample_rate_hz,
                          uint32_t n_samples,
                          uint64_t start_ts_unix_ms,
                          float scale_g_per_lsb);

} // namespace record_format
