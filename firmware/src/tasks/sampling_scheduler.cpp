#include "sampling_scheduler.h"

#include <Arduino.h>
#include <freertos/task.h>

namespace {

constexpr uint32_t kPeriodMs = 1000;
constexpr uint32_t kStackWords = 4096;
constexpr UBaseType_t kPriority = 3;

void taskFn(void* pv) {
    auto* ctx = static_cast<AppContext*>(pv);

    float lastBeaterA = 0.0f;
    float lastCompressorA = 0.0f;

    TickType_t lastWake = xTaskGetTickCount();
    for (;;) {
        const uint32_t nowMillis = millis();
        ctx->digitalInput->tickStub(nowMillis);

        const bool beaterOn = ctx->digitalInput->isActive(DigitalInputChannel::Beater);
        const bool compressorCmd = ctx->digitalInput->isActive(DigitalInputChannel::Contactor);
        const bool tccSatisfied = ctx->digitalInput->isActive(DigitalInputChannel::Tcc);
        const bool hpOk = ctx->digitalInput->isActive(DigitalInputChannel::Hp);
        ctx->compressorOn = compressorCmd;

        const float currentBeaterA = ctx->currentSensor->readRmsAmps(CurrentSensorAds1115::Channel::Beater);
        const float currentCompressorA = ctx->currentSensor->readRmsAmps(CurrentSensorAds1115::Channel::Compressor);

        ChannelRow row;
        row.ts_unix_ms = ctx->rtc->now_ms();
        row.current_beater_a = currentBeaterA;
        row.current_compressor_a = currentCompressorA;
        row.temp_cylinder_c = ctx->tempDs18b20->readC(TempDs18b20::Channel::Cylinder);
        row.temp_cond_in_c = ctx->tempDs18b20->readC(TempDs18b20::Channel::CondIn);
        row.temp_cond_out_c = ctx->tempDs18b20->readC(TempDs18b20::Channel::CondOut);
        row.temp_ambient_c = ctx->tempDs18b20->readC(TempDs18b20::Channel::Ambient);
        row.temp_hopper_c = ctx->tempDs18b20->readC(TempDs18b20::Channel::Hopper); // NAN, absent probe
        row.temp_discharge_c = ctx->thermocouple->readDischargeC(compressorCmd);
        row.beater_on = beaterOn;
        row.compressor_cmd = compressorCmd;
        row.tcc_satisfied = tccSatisfied;
        row.hp_ok = hpOk;

        SampleRecord rec;
        rec.type = RecordType::ChannelRow;
        rec.channel = row;
        if (ctx->sampleQueue != nullptr) {
            xQueueSend(ctx->sampleQueue, &rec, 0);
        }

        // Simple spike heuristic: a jump beyond config threshold since last
        // sample nudges vibration_capture to grab an out-of-cycle burst for
        // that pod. Real fault-detection logic is out of scope for M0.
        const float threshold = ctx->configLoader ? ctx->configLoader->config().current_spike_threshold_a : 5.0f;
        if ((currentBeaterA - lastBeaterA) > threshold) {
            ctx->vibTriggerBeater = true;
        }
        if ((currentCompressorA - lastCompressorA) > threshold) {
            ctx->vibTriggerCompressor = true;
        }
        lastBeaterA = currentBeaterA;
        lastCompressorA = currentCompressorA;

        vTaskDelayUntil(&lastWake, pdMS_TO_TICKS(kPeriodMs));
    }
}

} // namespace

void startSamplingSchedulerTask(AppContext* ctx) {
    xTaskCreate(taskFn, "sampling", kStackWords, ctx, kPriority, nullptr);
}
