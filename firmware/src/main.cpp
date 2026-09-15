// main.cpp - frosty-monitor M0 firmware entry point.
//
// setup() wires up every HAL stub + the SD sink + config, then starts the
// task pipeline (sampling_scheduler -> queue -> storage_writer, plus
// vibration_capture and ui_task as producers into the same queue). loop()
// just services the serial CLI (SETTIME/STATUS) and yields -- all real work
// happens in the FreeRTOS tasks.
#include <Arduino.h>

#include "app_context.h"
#include "pins.h"
#include "version.h"
#include "storage/ble_sink.h"
#include "storage/cloud_sink.h"
#include "storage/sd_sink.h"
#include "tasks/config_loader.h"
#include "tasks/sampling_scheduler.h"
#include "tasks/storage_writer.h"
#include "tasks/ui_task.h"
#include "tasks/vibration_capture.h"

namespace {

constexpr int kSampleQueueDepth = 64;

SdStorageSink g_sink;
RtcDs3231 g_rtc;
CurrentSensorAds1115 g_currentSensor;
TempDs18b20 g_tempDs18b20;
ThermocoupleMax31855 g_thermocouple;
DigitalInputHal g_digitalInput;
LeakSensorsHal g_leakSensors;
VibrationAdxl345 g_vibPodBeater(1, i2c_addr::ADXL345_POD_A);
VibrationAdxl345 g_vibPodCompressor(2, i2c_addr::ADXL345_POD_B);
ConfigLoader g_configLoader(&g_sink);

// CloudSink needs the effective config (in particular config.cloud), which
// only exists after ConfigLoader::loadOrDefault() runs -- so, unlike every
// other global above, it can't be constructed with its final config at
// static-init time. It's constructed in setup() instead once the config is
// available; see the comment there. BleSink has no config to wait for
// (it's a stub either way), so it stays a plain global like the HAL stubs.
CloudSink* g_cloudSink = nullptr;
BleSink g_bleSink;

AppContext g_ctx;

} // namespace

void setup() {
    Serial.begin(115200);
    uint32_t waitStart = millis();
    while (!Serial && (millis() - waitStart) < 2000) {
        delay(10); // give native USB CDC a moment to enumerate; don't hang forever
    }

    Serial.println();
    Serial.print("frosty-monitor firmware ");
    Serial.println(FIRMWARE_VERSION);
#if defined(FROSTY_DEV_MODE)
    Serial.println("[main] FROSTY_DEV_MODE: all sensor drivers are STUBs, vib capture interval shortened");
#endif

    // PSRAM: board_build.arduino.memory_type=qio_opi enables it via the
    // Arduino core; just confirm it actually came up since VibBurst buffers
    // depend on it (with a malloc() fallback, see vibration_capture.cpp).
    if (psramFound()) {
        Serial.printf("[main] PSRAM ok, %u bytes free\n", ESP.getFreePsram());
    } else {
        Serial.println("[main] WARNING: PSRAM not found; vib burst buffers will fall back to internal heap");
    }

    g_sink.begin(); // ok to fail (no card); pipeline still runs cardless
    g_rtc.begin();
    g_currentSensor.begin();
    g_tempDs18b20.begin();
    g_thermocouple.begin();
    g_digitalInput.begin();
    g_leakSensors.begin();
    g_vibPodBeater.begin();
    g_vibPodCompressor.begin();

    g_configLoader.loadOrDefault();
    g_configLoader.writeManifest(g_rtc);

    // CloudSink is constructed here, after loadOrDefault(), so it gets the
    // effective config.cloud (technician-authored config.json value if
    // present, CloudConfig{} defaults -- i.e. disabled -- otherwise). A
    // plain `new` with no matching delete is intentional and matches every
    // other global here: this object lives for the process's entire life.
    g_cloudSink = new CloudSink(g_configLoader.config().cloud);
    g_cloudSink->begin(); // no-op (no WiFi touched) unless config.cloud.enabled

    g_ctx.sampleQueue = xQueueCreate(kSampleQueueDepth, sizeof(SampleRecord));
    if (g_ctx.sampleQueue == nullptr) {
        Serial.println("[main] FATAL: failed to create sample queue");
    }

    g_ctx.sink = &g_sink;
    g_ctx.sinks[0] = &g_sink;       // primary / source of truth, always first
    g_ctx.sinks[1] = g_cloudSink;   // best-effort, disabled by default
    g_ctx.sinks[2] = &g_bleSink;    // stub -- isReady() always false, see ble_sink.h
    g_ctx.sinkCount = 3;
    g_ctx.rtc = &g_rtc;
    g_ctx.currentSensor = &g_currentSensor;
    g_ctx.tempDs18b20 = &g_tempDs18b20;
    g_ctx.thermocouple = &g_thermocouple;
    g_ctx.digitalInput = &g_digitalInput;
    g_ctx.leakSensors = &g_leakSensors;
    g_ctx.vibPodBeater = &g_vibPodBeater;
    g_ctx.vibPodCompressor = &g_vibPodCompressor;
    g_ctx.configLoader = &g_configLoader;

    startStorageWriterTask(&g_ctx);
    startSamplingSchedulerTask(&g_ctx);
    startVibrationCaptureTask(&g_ctx);
    startUiTask(&g_ctx);

    Serial.println("[main] tasks started");
}

void loop() {
    // All real work happens in FreeRTOS tasks; loop() just services the
    // serial CLI (SETTIME <iso8601>, STATUS) and yields.
    g_configLoader.pollSerialCli(g_rtc);
    delay(20);
}
