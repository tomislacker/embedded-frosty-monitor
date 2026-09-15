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
            if (ctx->sink != nullptr) {
                ctx->sink->write(rec);
            }
        }

        if ((xTaskGetTickCount() - lastFlush) >= pdMS_TO_TICKS(kFlushPeriodMs)) {
            if (ctx->sink != nullptr) {
                ctx->sink->flush();
            }
            lastFlush = xTaskGetTickCount();
        }
    }
}

} // namespace

void startStorageWriterTask(AppContext* ctx) {
    xTaskCreate(taskFn, "storage_writer", kStackWords, ctx, kPriority, nullptr);
}
