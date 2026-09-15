#include <unity.h>

#include <cmath>
#include <cstring>
#include <string>

#include "hal/digital_input.h"
#include "storage/record_format.h"
#include "storage/record_types.h"
#include "util/ring_buffer.h"

// ---- ring_buffer ----

void test_ring_buffer_push_pop_order() {
    RingBuffer<int, 4> rb;
    TEST_ASSERT_TRUE(rb.empty());
    rb.push(1);
    rb.push(2);
    rb.push(3);
    TEST_ASSERT_EQUAL_UINT32(3, rb.size());

    int v = 0;
    TEST_ASSERT_TRUE(rb.pop(&v));
    TEST_ASSERT_EQUAL_INT(1, v);
    TEST_ASSERT_TRUE(rb.pop(&v));
    TEST_ASSERT_EQUAL_INT(2, v);
    TEST_ASSERT_TRUE(rb.pop(&v));
    TEST_ASSERT_EQUAL_INT(3, v);
    TEST_ASSERT_FALSE(rb.pop(&v));
    TEST_ASSERT_TRUE(rb.empty());
}

void test_ring_buffer_wrap_overwrite() {
    RingBuffer<int, 3> rb;
    rb.push(1);
    rb.push(2);
    rb.push(3);
    TEST_ASSERT_TRUE(rb.full());
    rb.push(4); // overwrites oldest (1)
    TEST_ASSERT_TRUE(rb.full());
    TEST_ASSERT_EQUAL_UINT32(3, rb.size());

    int v = 0;
    TEST_ASSERT_TRUE(rb.pop(&v));
    TEST_ASSERT_EQUAL_INT(2, v);
    TEST_ASSERT_TRUE(rb.pop(&v));
    TEST_ASSERT_EQUAL_INT(3, v);
    TEST_ASSERT_TRUE(rb.pop(&v));
    TEST_ASSERT_EQUAL_INT(4, v);
    TEST_ASSERT_FALSE(rb.pop(&v));
}

// ---- record_format: channels CSV ----

void test_channels_csv_header_exact() {
    const std::string expected =
        "ts_iso,ts_unix_ms,current_beater_a,current_compressor_a,"
        "temp_cylinder_c,temp_cond_in_c,temp_cond_out_c,temp_ambient_c,"
        "temp_hopper_c,temp_discharge_c,beater_on,compressor_cmd,"
        "tcc_satisfied,hp_ok";
    TEST_ASSERT_EQUAL_STRING(expected.c_str(), record_format::channelsCsvHeader().c_str());
}

void test_vib_summary_csv_header_exact() {
    const std::string expected =
        "ts_iso,ts_unix_ms,pod_id,rms_x_g,rms_y_g,rms_z_g,peak_x_g,"
        "peak_y_g,peak_z_g,band_low_g2,band_mid_g2,band_high_g2";
    TEST_ASSERT_EQUAL_STRING(expected.c_str(), record_format::vibSummaryCsvHeader().c_str());
}

// Counts commas (== field count - 1) so field-count regressions are caught
// even if individual values change.
static size_t countFields(const std::string& csvLine) {
    size_t fields = 1;
    for (char c : csvLine) {
        if (c == ',') ++fields;
    }
    return fields;
}

void test_channel_row_csv_field_count() {
    ChannelRow row;
    row.ts_unix_ms = 1700000000000ULL;
    row.current_beater_a = 3.14f;
    row.current_compressor_a = 0.0f;
    row.temp_cylinder_c = 4.5f;
    row.temp_cond_in_c = 30.0f;
    row.temp_cond_out_c = 22.0f;
    row.temp_ambient_c = 21.0f;
    row.temp_hopper_c = NAN;
    row.temp_discharge_c = 80.0f;
    row.beater_on = true;
    row.compressor_cmd = false;
    row.tcc_satisfied = true;
    row.hp_ok = true;

    const std::string csv = record_format::formatChannelRowCsv(row);
    // ts_iso, ts_unix_ms, 8 float channels, 4 bool channels = 14 fields.
    TEST_ASSERT_EQUAL_UINT32(14, countFields(csv));
}

void test_channel_row_csv_nan_is_empty_field() {
    ChannelRow row;
    row.ts_unix_ms = 1700000000000ULL;
    row.temp_hopper_c = NAN;
    row.temp_cylinder_c = 5.0f;

    const std::string csv = record_format::formatChannelRowCsv(row);
    TEST_ASSERT_NOT_EQUAL(std::string::npos, csv.find(",5.000,")); // cylinder present
    TEST_ASSERT_NOT_EQUAL(std::string::npos, csv.find(",,")); // hopper empty field between two commas
}

void test_channel_row_csv_bools_are_0_1() {
    ChannelRow row;
    row.ts_unix_ms = 1700000000000ULL;
    row.beater_on = true;
    row.compressor_cmd = false;
    row.tcc_satisfied = true;
    row.hp_ok = false;

    const std::string csv = record_format::formatChannelRowCsv(row);
    TEST_ASSERT_TRUE(csv.size() > 4);
    TEST_ASSERT_EQUAL_STRING("1,0,1,0", csv.substr(csv.size() - 7).c_str());
}

void test_iso8601_format() {
    // 2023-11-14T22:13:20Z == 1700000000 unix seconds.
    const std::string iso = record_format::formatIso8601(1700000000000ULL);
    TEST_ASSERT_EQUAL_STRING("2023-11-14T22:13:20Z", iso.c_str());
}

// ---- record_format: vib burst binary header ----

void test_vib_burst_header_bytes() {
    uint8_t header[32];
    record_format::writeVibBurstHeader(header, /*pod_id=*/2, /*sample_rate_hz=*/400,
                                        /*n_samples=*/800, /*start_ts_unix_ms=*/1700000000000ULL,
                                        /*scale_g_per_lsb=*/0.0039f);

    TEST_ASSERT_EQUAL_UINT8('F', header[0]);
    TEST_ASSERT_EQUAL_UINT8('V', header[1]);
    TEST_ASSERT_EQUAL_UINT8('B', header[2]);
    TEST_ASSERT_EQUAL_UINT8('1', header[3]);
    TEST_ASSERT_EQUAL_UINT8(1, header[4]);   // version
    TEST_ASSERT_EQUAL_UINT8(2, header[5]);   // pod_id

    uint32_t sampleRate;
    std::memcpy(&sampleRate, &header[8], sizeof(sampleRate));
    TEST_ASSERT_EQUAL_UINT32(400, sampleRate);

    uint32_t nSamples;
    std::memcpy(&nSamples, &header[12], sizeof(nSamples));
    TEST_ASSERT_EQUAL_UINT32(800, nSamples);

    TEST_ASSERT_EQUAL_UINT8(3, header[16]); // n_axes

    uint64_t ts;
    std::memcpy(&ts, &header[20], sizeof(ts));
    TEST_ASSERT_EQUAL_UINT64(1700000000000ULL, ts);

    float scale;
    std::memcpy(&scale, &header[28], sizeof(scale));
    TEST_ASSERT_FLOAT_WITHIN(0.0001f, 0.0039f, scale);
}

// ---- digital_input windowed detection ----

void test_digital_input_active_after_enough_edges_in_window() {
    DigitalInputMonitor mon;
    TEST_ASSERT_FALSE(mon.isActive(DigitalInputChannel::Beater, 1000));

    mon.recordEdge(DigitalInputChannel::Beater, 1000);
    TEST_ASSERT_FALSE(mon.isActive(DigitalInputChannel::Beater, 1000)); // only 1 edge, below threshold

    mon.recordEdge(DigitalInputChannel::Beater, 1010);
    TEST_ASSERT_TRUE(mon.isActive(DigitalInputChannel::Beater, 1010)); // 2 edges within 100ms window
}

void test_digital_input_inactive_once_edges_age_out() {
    DigitalInputMonitor mon;
    mon.recordEdge(DigitalInputChannel::Contactor, 1000);
    mon.recordEdge(DigitalInputChannel::Contactor, 1010);
    TEST_ASSERT_TRUE(mon.isActive(DigitalInputChannel::Contactor, 1010));

    // 200ms later, both edges are outside the 100ms rolling window.
    TEST_ASSERT_FALSE(mon.isActive(DigitalInputChannel::Contactor, 1210));
    TEST_ASSERT_EQUAL_UINT8(0, mon.edgeCountInWindow(DigitalInputChannel::Contactor, 1210));
}

void test_digital_input_channels_are_independent() {
    DigitalInputMonitor mon;
    mon.recordEdge(DigitalInputChannel::Tcc, 5000);
    mon.recordEdge(DigitalInputChannel::Tcc, 5010);
    TEST_ASSERT_TRUE(mon.isActive(DigitalInputChannel::Tcc, 5010));
    TEST_ASSERT_FALSE(mon.isActive(DigitalInputChannel::Hp, 5010));
}

void test_digital_input_millis_rollover_safe() {
    DigitalInputMonitor mon;
    // Edge recorded just before a uint32_t millis() rollover...
    const uint32_t justBeforeRollover = 0xFFFFFFF0u;
    mon.recordEdge(DigitalInputChannel::Hp, justBeforeRollover);
    mon.recordEdge(DigitalInputChannel::Hp, justBeforeRollover + 5); // wraps past UINT32_MAX
    TEST_ASSERT_TRUE(mon.isActive(DigitalInputChannel::Hp, justBeforeRollover + 5));
}

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;

    UNITY_BEGIN();

    RUN_TEST(test_ring_buffer_push_pop_order);
    RUN_TEST(test_ring_buffer_wrap_overwrite);

    RUN_TEST(test_channels_csv_header_exact);
    RUN_TEST(test_vib_summary_csv_header_exact);
    RUN_TEST(test_channel_row_csv_field_count);
    RUN_TEST(test_channel_row_csv_nan_is_empty_field);
    RUN_TEST(test_channel_row_csv_bools_are_0_1);
    RUN_TEST(test_iso8601_format);
    RUN_TEST(test_vib_burst_header_bytes);

    RUN_TEST(test_digital_input_active_after_enough_edges_in_window);
    RUN_TEST(test_digital_input_inactive_once_edges_age_out);
    RUN_TEST(test_digital_input_channels_are_independent);
    RUN_TEST(test_digital_input_millis_rollover_safe);

    return UNITY_END();
}
