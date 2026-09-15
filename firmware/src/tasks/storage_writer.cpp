#include "storage_writer.h"

#include <Arduino.h>
#include <freertos/task.h>

namespace {

constexpr uint32_t kStackWords = 6144;
constexpr UBaseType_t kPriority = 4; // highest of the data-path tasks: drain promptly, queue is bounded
constexpr uint32_t kFlushPeriodMs = 5000;

void taskFn(void* pv) {
    auto* ctx = static_cast<AppContext*>(pv);

    SampleRecord rec;
    TickType_t lastFlush = xTaskGetTickCount();

    for (;;) {
        if (ctx->sampleQueue != nullptr &&
            xQueueReceive(ctx->sampleQueue, &rec, pdMS_TO_TICKS(200)) == pdTRUE) {
            // Tee to every configured sink (sinks[0] is always SD, the
            // source of truth). Each sink's write() is independent -- one
            // sink failing (cloud down, a future BLE sink not connected,
            // whatever) must never block or corrupt any other sink's write,
            // so failures are swallowed per-sink here rather than
            // short-circuiting the loop. See
            // docs/firmware/connectivity.md for the multi-sink design.
            for (size_t i = 0; i < ctx->sinkCount; ++i) {
                IStorageSink* s = ctx->sinks[i];
                if (s != nullptr) {
                    s->write(rec);
                }
            }
        }

        if ((xTaskGetTickCount() - lastFlush) >= pdMS_TO_TICKS(kFlushPeriodMs)) {
            for (size_t i = 0; i < ctx->sinkCount; ++i) {
                if (ctx->sinks[i] != nullptr) {
                    ctx->sinks[i]->flush();
                }
            }
            lastFlush = xTaskGetTickCount();
        }
    }
}

} // namespace

void startStorageWriterTask(AppContext* ctx) {
    xTaskCreate(taskFn, "storage_writer", kStackWords, ctx, kPriority, nullptr);
}
