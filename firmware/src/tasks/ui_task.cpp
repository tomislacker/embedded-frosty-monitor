#include "ui_task.h"

#include <Arduino.h>
#include <freertos/task.h>
#include <cstdio>

#include "../pins.h"

namespace {

constexpr uint32_t kStackWords = 3072;
constexpr UBaseType_t kPriority = 1;
constexpr uint32_t kPollPeriodMs = 20;
constexpr uint32_t kDebounceStableMs = 30;
constexpr uint32_t kHeartbeatPeriodMs = 1000;

// Simple time-based button debouncer. Buttons are wired active-low with
// internal pullups.
class DebouncedButton {
public:
    explicit DebouncedButton(uint8_t pin) : pin_(pin) {}

    void begin() { pinMode(pin_, INPUT_PULLUP); }

    // Returns true exactly once per confirmed press (falling edge that held
    // stable for kDebounceStableMs).
    bool pollPressed(uint32_t nowMs) {
        const bool rawPressed = (digitalRead(pin_) == LOW);
        if (rawPressed != lastRaw_) {
            lastRaw_ = rawPressed;
            lastChangeMs_ = nowMs;
        }

        bool firedPress = false;
        if ((nowMs - lastChangeMs_) >= kDebounceStableMs && rawPressed != stable_) {
            stable_ = rawPressed;
            if (stable_) {
                firedPress = true;
            }
        }
        return firedPress;
    }

private:
    uint8_t pin_;
    bool lastRaw_ = false;
    bool stable_ = false;
    uint32_t lastChangeMs_ = 0;
};

void enqueueButtonEvent(AppContext* ctx, const char* button) {
    Event e;
    e.ts_unix_ms = ctx->rtc->now_ms();
    std::snprintf(e.type, sizeof(e.type), "button");
    std::snprintf(e.detail_json, sizeof(e.detail_json), "{\"button\":\"%s\"}", button);

    SampleRecord rec;
    rec.type = RecordType::Event;
    rec.event = e;
    if (ctx->sampleQueue != nullptr) {
        xQueueSend(ctx->sampleQueue, &rec, 0);
    }
}

void taskFn(void* pv) {
    auto* ctx = static_cast<AppContext*>(pv);

    pinMode(pins::LED_REC, OUTPUT);
    pinMode(pins::LED_ERR, OUTPUT);
    pinMode(pins::LED_CARD, OUTPUT);

    DebouncedButton journalBtn(pins::BTN_JOURNAL);
    DebouncedButton spareBtn(pins::BTN_SPARE);
    journalBtn.begin();
    spareBtn.begin();

    uint32_t lastHeartbeatToggle = 0;
    bool heartbeatOn = false;

    for (;;) {
        const uint32_t nowMs = millis();

        if (journalBtn.pollPressed(nowMs)) {
            enqueueButtonEvent(ctx, "journal");
        }
        // STUB(M1): spare button debounced but unmapped; wire an action
        // (e.g. mark-event-without-journal-prompt, or a shift key) later.
        spareBtn.pollPressed(nowMs);

        const bool cardReady = (ctx->sink != nullptr) && ctx->sink->isReady();
        digitalWrite(pins::LED_CARD, cardReady ? HIGH : LOW);
        // M0's only error signal is "no card"; more sources land in M1.
        digitalWrite(pins::LED_ERR, cardReady ? LOW : HIGH);

        if ((nowMs - lastHeartbeatToggle) >= (kHeartbeatPeriodMs / 2)) {
            heartbeatOn = !heartbeatOn;
            lastHeartbeatToggle = nowMs;
        }
        digitalWrite(pins::LED_REC, (cardReady && heartbeatOn) ? HIGH : LOW);

        vTaskDelay(pdMS_TO_TICKS(kPollPeriodMs));
    }
}

} // namespace

void startUiTask(AppContext* ctx) {
    xTaskCreate(taskFn, "ui_task", kStackWords, ctx, kPriority, nullptr);
}
