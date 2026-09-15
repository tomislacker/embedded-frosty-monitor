#include "config_loader.h"

#include <ArduinoJson.h>
#include <Arduino.h>
#include <SD.h>

#include "../version.h"
#include "../storage/record_format.h"
#include "../storage/sd_sink.h"

ConfigLoader::ConfigLoader(IStorageSink* sink) : sink_(sink) {}

void ConfigLoader::loadOrDefault() {
    config_ = AppConfig{}; // start from defaults

#if defined(FROSTY_DEV_MODE)
    config_.vib_capture_interval_s = 15;
#endif

    if (!sink_ || !sink_->isReady()) {
        Serial.println("[config_loader] no card; using default config");
        return;
    }

    xSemaphoreTake(sdSpiMutex(), portMAX_DELAY);
    File f = SD.open("/config.json", FILE_READ);
    if (!f) {
        xSemaphoreGive(sdSpiMutex());
        Serial.println("[config_loader] /config.json absent; using defaults");
        return;
    }

    JsonDocument doc;
    const DeserializationError err = deserializeJson(doc, f);
    f.close();
    xSemaphoreGive(sdSpiMutex());

    if (err) {
        Serial.printf("[config_loader] /config.json parse error: %s; using defaults\n", err.c_str());
        return;
    }

    config_.deployment_id = doc["deployment_id"] | config_.deployment_id.c_str();
    config_.machine_model = doc["machine_model"] | config_.machine_model.c_str();
    config_.machine_serial = doc["machine_serial"] | config_.machine_serial.c_str();
    config_.technician = doc["technician"] | config_.technician.c_str();
    config_.vib_capture_interval_s = doc["vib_capture_interval_s"] | config_.vib_capture_interval_s;
    config_.vib_burst_duration_s = doc["vib_burst_duration_s"] | config_.vib_burst_duration_s;
    config_.vib_sample_rate_hz = doc["vib_sample_rate_hz"] | config_.vib_sample_rate_hz;
    config_.current_spike_threshold_a = doc["current_spike_threshold_a"] | config_.current_spike_threshold_a;

    // "cloud" object is entirely optional; every field defaults per
    // CloudConfig (cloud_config.h) when the object -- or any individual
    // field within it -- is absent. In particular cloud.enabled defaults to
    // false, so an old config.json with no "cloud" key at all is exactly
    // equivalent to an explicit {"cloud":{"enabled":false}}.
    JsonObjectConst cloud = doc["cloud"];
    config_.cloud.enabled = cloud["enabled"] | config_.cloud.enabled;
    config_.cloud.wifi_ssid = cloud["wifi_ssid"] | config_.cloud.wifi_ssid.c_str();
    config_.cloud.wifi_pass = cloud["wifi_pass"] | config_.cloud.wifi_pass.c_str();
    config_.cloud.mqtt_host = cloud["mqtt_host"] | config_.cloud.mqtt_host.c_str();
    config_.cloud.mqtt_port = cloud["mqtt_port"] | config_.cloud.mqtt_port;
    config_.cloud.client_id = cloud["client_id"] | config_.cloud.client_id.c_str();
    config_.cloud.topic_prefix = cloud["topic_prefix"] | config_.cloud.topic_prefix.c_str();
    config_.cloud.publish_interval_s = cloud["publish_interval_s"] | config_.cloud.publish_interval_s;
    config_.cloud.ca_path = cloud["ca_path"] | config_.cloud.ca_path.c_str();
    config_.cloud.cert_path = cloud["cert_path"] | config_.cloud.cert_path.c_str();
    config_.cloud.key_path = cloud["key_path"] | config_.cloud.key_path.c_str();
    // A technician shouldn't have to name the deployment twice; fall back to
    // deployment_id if config.json's "cloud" object didn't set its own
    // client_id (or omitted "cloud" entirely).
    if (config_.cloud.client_id.empty()) {
        config_.cloud.client_id = config_.deployment_id;
    }

    Serial.println("[config_loader] loaded /config.json");
}

void ConfigLoader::writeManifest(RtcDs3231& rtc) {
    if (!sink_ || !sink_->isReady()) {
        Serial.println("[config_loader] no card; skipping manifest.json");
        return;
    }

    startTsIso_ = record_format::formatIso8601(rtc.now_ms());

    JsonDocument doc;
    doc["schema_version"] = 1;
    doc["deployment_id"] = config_.deployment_id;
    doc["machine_model"] = config_.machine_model;
    doc["machine_serial"] = config_.machine_serial;
    doc["technician"] = config_.technician;
    doc["firmware_version"] = FIRMWARE_VERSION;
    doc["start_ts_iso"] = startTsIso_;
    doc["channel_map"].to<JsonObject>();
    JsonObject effective = doc["config_effective"].to<JsonObject>();
    effective["vib_capture_interval_s"] = config_.vib_capture_interval_s;
    effective["vib_burst_duration_s"] = config_.vib_burst_duration_s;
    effective["vib_sample_rate_hz"] = config_.vib_sample_rate_hz;
    effective["current_spike_threshold_a"] = config_.current_spike_threshold_a;

    xSemaphoreTake(sdSpiMutex(), portMAX_DELAY);
    File f = SD.open("/manifest.json", FILE_WRITE);
    if (f) {
        serializeJsonPretty(doc, f);
        f.close();
        Serial.println("[config_loader] wrote /manifest.json");
    } else {
        Serial.println("[config_loader] failed to open /manifest.json for write");
    }
    xSemaphoreGive(sdSpiMutex());
}

void ConfigLoader::pollSerialCli(RtcDs3231& rtc) {
    while (Serial.available() > 0) {
        const char c = static_cast<char>(Serial.read());
        if (c == '\n' || c == '\r') {
            if (!lineBuf_.empty()) {
                handleCliLine(lineBuf_, rtc);
                lineBuf_.clear();
            }
        } else {
            lineBuf_ += c;
            if (lineBuf_.size() > 200) {
                lineBuf_.clear(); // guard against a runaway/garbage line
            }
        }
    }
}

void ConfigLoader::handleCliLine(const std::string& line, RtcDs3231& rtc) {
    if (line.rfind("SETTIME ", 0) == 0) {
        const std::string iso = line.substr(8);
        if (rtc.setTime(iso.c_str())) {
            Serial.print("OK settime ");
            Serial.println(iso.c_str());
        } else {
            Serial.print("ERR settime parse failure: ");
            Serial.println(iso.c_str());
        }
        return;
    }

    if (line == "STATUS") {
        Serial.println("--- STATUS ---");
        Serial.print("firmware_version="); Serial.println(FIRMWARE_VERSION);
        Serial.print("now_iso="); Serial.println(record_format::formatIso8601(rtc.now_ms()).c_str());
        Serial.print("sd_ready="); Serial.println(sink_ && sink_->isReady() ? "1" : "0");
        Serial.print("deployment_id="); Serial.println(config_.deployment_id.c_str());
        Serial.print("machine_model="); Serial.println(config_.machine_model.c_str());
        Serial.print("machine_serial="); Serial.println(config_.machine_serial.c_str());
        Serial.print("vib_capture_interval_s="); Serial.println(config_.vib_capture_interval_s);
        Serial.println("--------------");
        return;
    }

    Serial.print("ERR unknown command: ");
    Serial.println(line.c_str());
}
