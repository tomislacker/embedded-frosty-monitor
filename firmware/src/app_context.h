// app_context.h - shared handles/state passed to every FreeRTOS task.
//
// Owned and constructed once in main.cpp::setup(); tasks receive a pointer
// to this struct as their pvParameters. Keeping this in one place avoids
// scattering `extern` globals across the task modules.
#pragma once

#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

#include "hal/current_sensor_ads1115.h"
#include "hal/digital_input.h"
#include "hal/i_storage_sink.h"
#include "hal/leak_sensors.h"
#include "hal/rtc_ds3231.h"
#include "hal/temp_ds18b20.h"
#include "hal/temp_thermocouple_max31855.h"
#include "hal/vibration_adxl345.h"
#include "tasks/config_loader.h"

struct AppContext {
    QueueHandle_t sampleQueue = nullptr;

    // `sink` is specifically the primary SD sink -- kept as its own field
    // (rather than just sinks[0]) because a couple of call sites care about
    // *SD* readiness specifically, not "is anything ready": ui_task's card
    // LED, and config_loader's config.json/manifest.json access (which goes
    // straight through SD.h, not through the sink interface, but still
    // gates on this same pointer's isReady()).
    IStorageSink* sink = nullptr;

    // Every sink StorageWriterTask tees each record to -- see
    // tasks/storage_writer.cpp and docs/firmware/connectivity.md for the
    // multi-sink tee architecture. Index 0 is always `sink` above (SD, the
    // source of truth); any other slot is best-effort (CloudSink today,
    // BleSink once implemented) and a failure there must never block or
    // corrupt SD's write. Fixed-size array, not a vector, to avoid a heap
    // allocation for something with a small, compile-time-known upper bound.
    static constexpr size_t kMaxStorageSinks = 3; // SD + Cloud + (future) BLE
    IStorageSink* sinks[kMaxStorageSinks] = {nullptr, nullptr, nullptr};
    size_t sinkCount = 0;

    RtcDs3231* rtc = nullptr;
    CurrentSensorAds1115* currentSensor = nullptr;
    TempDs18b20* tempDs18b20 = nullptr;
    ThermocoupleMax31855* thermocouple = nullptr;
    DigitalInputHal* digitalInput = nullptr;
    LeakSensorsHal* leakSensors = nullptr;
    VibrationAdxl345* vibPodBeater = nullptr;
    VibrationAdxl345* vibPodCompressor = nullptr;
    ConfigLoader* configLoader = nullptr;

    // Set by sampling_scheduler when it sees a current spike; consumed
    // (and cleared) by vibration_capture to trigger an out-of-cycle burst.
    volatile bool vibTriggerBeater = false;
    volatile bool vibTriggerCompressor = false;

    // Latest compressor-cmd state, shared so the thermocouple stub can
    // decide which temperature band to wander in.
    volatile bool compressorOn = false;
};
