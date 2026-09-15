#include "vibration_capture.h"

#include <Arduino.h>
#include <esp_heap_caps.h>
#include <freertos/task.h>
#include <cmath>
#include <cstdlib>

namespace {

constexpr uint32_t kStackWords = 8192;
constexpr UBaseType_t kPriority = 2;

// Send the raw .bin burst to storage every Nth capture (plus always on an
// out-of-cycle spike trigger); the VibSummary is sent every capture
// regardless. Keeps steady-state SD usage down without losing the summary
// trend line.
constexpr uint32_t kBurstEveryNCaptures = 4;

struct AxisStats {
    float rms = 0.0f;
    float peak = 0.0f;
};

// Allocates the burst buffer in PSRAM (MALLOC_CAP_SPIRAM) with a plain
// malloc() fallback so the exact same call links and runs host-side too
// (native env has no heap_caps_malloc; that path is compiled out there
// since this whole file is Arduino/ESP-IDF only and isn't part of the
// native build filter).
int16_t* allocBurstBuffer(size_t nInt16) {
    void* p = heap_caps_malloc(nInt16 * sizeof(int16_t), MALLOC_CAP_SPIRAM);
    if (p == nullptr) {
        p = malloc(nInt16 * sizeof(int16_t));
    }
    return static_cast<int16_t*>(p);
}

AxisStats computeAxisStats(const int16_t* buf, uint32_t nSamples, uint8_t axis, uint8_t nAxes, float scaleGPerLsb) {
    AxisStats stats;
    if (nSamples == 0) return stats;

    double sumSq = 0.0;
    float peak = 0.0f;
    for (uint32_t i = 0; i < nSamples; ++i) {
        const float g = buf[i * nAxes + axis] * scaleGPerLsb;
        sumSq += static_cast<double>(g) * g;
        const float a = fabsf(g);
        if (a > peak) peak = a;
    }
    stats.rms = static_cast<float>(std::sqrt(sumSq / nSamples));
    stats.peak = peak;
    return stats;
}

// STUB(M1)/placeholder: real band-energy computation belongs on esp-dsp
// (Goertzel or FFT) once that dependency is added. For M0 we approximate
// "energy in three bands" by splitting the burst into three equal-length
// time chunks and summing squared combined-magnitude per chunk. This is
// NOT a real frequency-domain decomposition -- it exists purely so the
// VibSummary CSV has plausible, monotonically-sane-looking values to
// validate the pipeline/analysis tooling against.
void computeBandEnergies(const int16_t* buf, uint32_t nSamples, uint8_t nAxes, float scaleGPerLsb,
                          float* bandLowG2, float* bandMidG2, float* bandHighG2) {
    float* out[3] = {bandLowG2, bandMidG2, bandHighG2};
    if (nSamples == 0) {
        *bandLowG2 = *bandMidG2 = *bandHighG2 = 0.0f;
        return;
    }

    const uint32_t chunk = nSamples / 3;
    for (int band = 0; band < 3; ++band) {
        const uint32_t start = chunk * band;
        const uint32_t end = (band == 2) ? nSamples : (start + chunk);
        double sumSq = 0.0;
        for (uint32_t i = start; i < end; ++i) {
            for (uint8_t axis = 0; axis < nAxes; ++axis) {
                const float g = buf[i * nAxes + axis] * scaleGPerLsb;
                sumSq += static_cast<double>(g) * g;
            }
        }
        *out[band] = static_cast<float>(sumSq);
    }
}

void captureOnePod(AppContext* ctx, VibrationAdxl345* pod, bool sendBurst) {
    const AppConfig& cfg = ctx->configLoader->config();
    const uint32_t sampleRateHz = cfg.vib_sample_rate_hz;
    const uint32_t nSamples = cfg.vib_burst_duration_s * sampleRateHz;
    const uint8_t nAxes = 3;

    int16_t* buf = allocBurstBuffer(static_cast<size_t>(nSamples) * nAxes);
    if (buf == nullptr) {
        Serial.println("[vibration_capture] buffer alloc failed, skipping capture");
        return;
    }

    pod->fillBurst(buf, nSamples, sampleRateHz);

    const uint64_t ts = ctx->rtc->now_ms();
    const float scale = pod->scaleGPerLsb();

    VibSummary summary;
    summary.ts_unix_ms = ts;
    summary.pod_id = pod->podId();
    const AxisStats x = computeAxisStats(buf, nSamples, 0, nAxes, scale);
    const AxisStats y = computeAxisStats(buf, nSamples, 1, nAxes, scale);
    const AxisStats z = computeAxisStats(buf, nSamples, 2, nAxes, scale);
    summary.rms_x_g = x.rms; summary.rms_y_g = y.rms; summary.rms_z_g = z.rms;
    summary.peak_x_g = x.peak; summary.peak_y_g = y.peak; summary.peak_z_g = z.peak;
    computeBandEnergies(buf, nSamples, nAxes, scale, &summary.band_low_g2, &summary.band_mid_g2, &summary.band_high_g2);

    SampleRecord summaryRec;
    summaryRec.type = RecordType::VibSummary;
    summaryRec.vibSummary = summary;
    if (ctx->sampleQueue != nullptr) {
        xQueueSend(ctx->sampleQueue, &summaryRec, 0);
    }

    if (sendBurst) {
        VibBurst burst;
        burst.start_ts_unix_ms = ts;
        burst.pod_id = pod->podId();
        burst.sample_rate_hz = sampleRateHz;
        burst.n_samples = nSamples;
        burst.n_axes = nAxes;
        burst.scale_g_per_lsb = scale;
        burst.data = buf; // ownership transfers to the queue/storage_writer

        SampleRecord burstRec;
        burstRec.type = RecordType::VibBurst;
        burstRec.vibBurst = burst;
        if (ctx->sampleQueue == nullptr || xQueueSend(ctx->sampleQueue, &burstRec, 0) != pdTRUE) {
            // Queue full/absent: we still own the buffer, free it here per
            // the VibBurst ownership contract in record_types.h.
            free(buf);
        }
    } else {
        free(buf);
    }
}

void taskFn(void* pv) {
    auto* ctx = static_cast<AppContext*>(pv);
    uint32_t captureCount = 0;

    for (;;) {
        const uint32_t intervalS = ctx->configLoader ? ctx->configLoader->config().vib_capture_interval_s : 300;
        const bool triggeredBeater = ctx->vibTriggerBeater;
        const bool triggeredCompressor = ctx->vibTriggerCompressor;
        ctx->vibTriggerBeater = false;
        ctx->vibTriggerCompressor = false;

        const bool sendBurstThisCycle = (captureCount % kBurstEveryNCaptures) == 0;

        captureOnePod(ctx, ctx->vibPodBeater, sendBurstThisCycle || triggeredBeater);
        captureOnePod(ctx, ctx->vibPodCompressor, sendBurstThisCycle || triggeredCompressor);

        ++captureCount;
        vTaskDelay(pdMS_TO_TICKS(intervalS * 1000));
    }
}

} // namespace

void startVibrationCaptureTask(AppContext* ctx) {
    xTaskCreate(taskFn, "vib_capture", kStackWords, ctx, kPriority, nullptr);
}
