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

    IStorageSink* sink = nullptr;
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
