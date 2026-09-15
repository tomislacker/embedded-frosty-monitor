// record_types.h - wire/queue record definitions for the sampling pipeline.
//
// Deliberately Arduino-free (only <cstdint>) so it can be included from both
// the native unit tests and the esp32 firmware. Every record carries its own
// ts_unix_ms; ts_iso (human readable) is derived at format time, not stored,
// to keep these structs small/fixed-size and queue-friendly.
#pragma once

#include <cstdint>

// Discriminant for the SampleRecord tagged union below.
enum class RecordType : uint8_t {
    ChannelRow = 0,
    VibSummary = 1,
    VibBurst = 2,
    Event = 3,
};

// One row of the 1Hz channels_YYYYMMDD.csv stream.
struct ChannelRow {
    uint64_t ts_unix_ms = 0;
    float current_beater_a = 0.0f;
    float current_compressor_a = 0.0f;
    float temp_cylinder_c = 0.0f;
    float temp_cond_in_c = 0.0f;
    float temp_cond_out_c = 0.0f;
    float temp_ambient_c = 0.0f;
    float temp_hopper_c = 0.0f;   // NAN when the hopper probe is absent
    float temp_discharge_c = 0.0f;
    bool beater_on = false;
    bool compressor_cmd = false;
    bool tcc_satisfied = false;
    bool hp_ok = false;
};

// One row of vibration/vib_summary_YYYYMMDD.csv, emitted every capture.
struct VibSummary {
    uint64_t ts_unix_ms = 0;
    uint8_t pod_id = 0; // 1 = beater, 2 = compressor
    float rms_x_g = 0.0f;
    float rms_y_g = 0.0f;
    float rms_z_g = 0.0f;
    float peak_x_g = 0.0f;
    float peak_y_g = 0.0f;
    float peak_z_g = 0.0f;
    float band_low_g2 = 0.0f;
    float band_mid_g2 = 0.0f;
    float band_high_g2 = 0.0f;
};

// A raw burst capture. `data` points at a PSRAM (or host-heap) buffer of
// n_samples * n_axes interleaved int16_t samples (XYZXYZ...).
//
// Ownership: the buffer is allocated by vibration_capture (heap_caps_malloc
// with MALLOC_CAP_SPIRAM on-target, malloc() fallback so the same code links
// host-side). Once this struct is enqueued, ownership transfers with it:
// storage_writer frees the buffer with free() immediately after writing the
// .bin file. Any code path that discards a VibBurst record instead of
// writing it (queue full, shutdown, etc.) MUST free() the buffer itself.
struct VibBurst {
    uint64_t start_ts_unix_ms = 0;
    uint8_t pod_id = 0;
    uint32_t sample_rate_hz = 0;
    uint32_t n_samples = 0; // per axis
    uint8_t n_axes = 3;
    float scale_g_per_lsb = 0.0f;
    int16_t* data = nullptr; // see ownership note above
};

// Journal/system/trigger/error record for events_YYYYMMDD.jsonl.
struct Event {
    uint64_t ts_unix_ms = 0;
    char type[16] = {0};        // "button" | "system" | "trigger" | "error"
    char detail_json[128] = {0}; // raw JSON object text, e.g. {"button":"journal"}
};

// Fixed-size tagged union sent over the sampling->storage FreeRTOS queue.
// All members are trivial (no owning containers) so this type is POD and
// safe to copy byte-for-byte via xQueueSend/xQueueReceive.
struct SampleRecord {
    RecordType type = RecordType::ChannelRow;
    union {
        ChannelRow channel;
        VibSummary vibSummary;
        VibBurst vibBurst;
        Event event;
    };

    SampleRecord() : type(RecordType::ChannelRow), channel() {}
};
