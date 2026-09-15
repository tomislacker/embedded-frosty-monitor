#include "cloud_sink.h"

#ifdef ARDUINO

#include <Arduino.h>
#include <ArduinoJson.h>
#include <SD.h>
#include <freertos/task.h>

#include "record_format.h"
#include "sd_sink.h" // sdSpiMutex()

namespace {

constexpr const char* kWatermarkPath = "/cloud_watermark.json";

bool readFileToString(const char* path, std::string& out) {
    File f = SD.open(path, FILE_READ);
    if (!f) {
        return false;
    }
    out.clear();
    out.reserve(f.size());
    while (f.available()) {
        out += static_cast<char>(f.read());
    }
    f.close();
    return true;
}

void cloudSinkTaskFn(void* pv) {
    auto* self = static_cast<CloudSink*>(pv);
    for (;;) {
        self->poll();
        vTaskDelay(pdMS_TO_TICKS(250));
    }
}

} // namespace

CloudSink::CloudSink(const CloudConfig& cfg) : cfg_(cfg), mqtt_(tlsClient_) {}

CloudSink::~CloudSink() {
    if (aggMutex_ != nullptr) {
        vSemaphoreDelete(aggMutex_);
    }
}

bool CloudSink::write(const SampleRecord& record) {
    if (!cfg_.enabled) {
        return false;
    }

    switch (record.type) {
        case RecordType::ChannelRow: {
            xSemaphoreTake(aggMutex_, portMAX_DELAY);
            channelAgg_.add(record.channel);
            xSemaphoreGive(aggMutex_);
            return true;
        }
        case RecordType::VibSummary: {
            xSemaphoreTake(aggMutex_, portMAX_DELAY);
            if (record.vibSummary.pod_id == 1) {
                vibAggBeater_.add(record.vibSummary);
            } else {
                vibAggCompressor_.add(record.vibSummary);
            }
            xSemaphoreGive(aggMutex_);
            return true;
        }
        case RecordType::Event:
            // Events matter most near-real-time (an alarm, a journal button
            // press); publish immediately instead of folding into the
            // periodic aggregate. Best-effort: if not currently connected,
            // this just doesn't publish -- SD (sinks[0]) already has it
            // durably, which is the whole point of SD being the source of
            // truth.
            return publishEventNow(record.event);
        case RecordType::VibBurst:
            // Raw vibration bursts are never published -- SD only, by
            // design (see docs/firmware/connectivity.md#bandwidth for the
            // size math on why). Deliberately does not touch
            // record.vibBurst.data: per record_types.h's VibBurst ownership
            // contract, SD (sinks[0], processed as part of the same tee in
            // tasks/storage_writer.cpp) is the sole owner/freer of that
            // buffer -- this sink must never free it too.
            return false;
    }
    return false;
}

void CloudSink::flush() {
    // Intentionally a no-op. The SD flush cadence (~5s, see
    // tasks/storage_writer.cpp) exists to bound power-loss data exposure on
    // a physical medium. CloudSink's publish cadence is a separate, much
    // coarser knob (cfg_.publish_interval_s, minutes not seconds) driven by
    // the background task started in begin(). Forcing a publish here would
    // couple two unrelated cadences for no benefit, and risk blocking
    // StorageWriterTask on network I/O -- exactly what the background-task
    // design in begin() exists to avoid.
}

bool CloudSink::isReady() const {
    return cfg_.enabled && state_ == State::Connected;
}

void CloudSink::begin() {
    if (started_) {
        return;
    }
    started_ = true;

    if (!cfg_.enabled) {
        Serial.println("[cloud_sink] disabled (config.cloud.enabled=false); not touching WiFi");
        return;
    }

    aggMutex_ = xSemaphoreCreateMutex();
    loadWatermark();

    mqtt_.setServer(cfg_.mqtt_host.c_str(), cfg_.mqtt_port);
    mqtt_.setBufferSize(1024); // matches -DMQTT_MAX_PACKET_SIZE=1024, see platformio.ini

    enterState(State::Idle);

    // Deliberately its own low-priority task, not pumped inline from
    // StorageWriterTask -- see the class comment in cloud_sink.h for why.
    xTaskCreate(cloudSinkTaskFn, "cloud_sink", 6144, this, /*priority=*/1, nullptr);

    Serial.println("[cloud_sink] enabled; background connect task started");
}

void CloudSink::enterState(State s) {
    state_ = s;
    stateEnteredMs_ = millis();
}

void CloudSink::enterBackoff() {
    enterState(State::Backoff);
}

void CloudSink::poll() {
    if (!cfg_.enabled) {
        return;
    }

    const uint32_t now = millis();

    switch (state_) {
        case State::Idle: {
            WiFi.mode(WIFI_STA);
            WiFi.begin(cfg_.wifi_ssid.c_str(), cfg_.wifi_pass.c_str());
            enterState(State::WifiConnecting);
            break;
        }
        case State::WifiConnecting: {
            if (WiFi.status() == WL_CONNECTED) {
                enterState(State::WifiConnected);
            } else if (now - stateEnteredMs_ > kWifiConnectTimeoutMs) {
                Serial.println("[cloud_sink] WiFi connect timed out");
                enterBackoff();
            }
            break;
        }
        case State::WifiConnected: {
            if (beginMqttConnect()) {
                enterState(State::MqttConnecting);
            } else {
                enterBackoff();
            }
            break;
        }
        case State::MqttConnecting: {
            if (mqtt_.connected()) {
                Serial.println("[cloud_sink] MQTT connected");
                backoffMs_ = kBackoffInitialMs; // reset backoff on a clean connect
                enterState(State::Connected);
                backfillFromSd(); // TODO(M2): documented no-op today
            } else if (now - stateEnteredMs_ > kMqttConnectTimeoutMs) {
                Serial.println("[cloud_sink] MQTT connect timed out");
                enterBackoff();
            }
            break;
        }
        case State::Connected: {
            if (WiFi.status() != WL_CONNECTED || !mqtt_.connected()) {
                Serial.println("[cloud_sink] connection dropped");
                enterBackoff();
                break;
            }
            mqtt_.loop();
            maybePublish(now);
            break;
        }
        case State::Backoff: {
            if (now - stateEnteredMs_ > backoffMs_) {
                backoffMs_ = (backoffMs_ < kBackoffMaxMs / 2) ? backoffMs_ * 2 : kBackoffMaxMs;
                enterState(State::Idle);
            }
            break;
        }
    }
}

bool CloudSink::loadCertsFromSd() {
    if (certsLoaded_) {
        return true;
    }

    xSemaphoreTake(sdSpiMutex(), portMAX_DELAY);
    const bool ok = readFileToString(cfg_.ca_path.c_str(), caCert_) &&
                     readFileToString(cfg_.cert_path.c_str(), clientCert_) &&
                     readFileToString(cfg_.key_path.c_str(), clientKey_);
    xSemaphoreGive(sdSpiMutex());

    if (!ok) {
        Serial.println("[cloud_sink] failed to load TLS certs from SD (card absent, or /certs/* missing); will retry");
        return false;
    }
    certsLoaded_ = true;
    return true;
}

bool CloudSink::beginMqttConnect() {
    if (!loadCertsFromSd()) {
        return false;
    }

    tlsClient_.setCACert(caCert_.c_str());
    tlsClient_.setCertificate(clientCert_.c_str());
    tlsClient_.setPrivateKey(clientKey_.c_str());

    const std::string clientId = cfg_.client_id.empty() ? std::string("frosty-monitor") : cfg_.client_id;
    // Blocking (TCP + TLS handshake): fine here, this runs on the dedicated
    // background task from begin(), never on StorageWriterTask.
    return mqtt_.connect(clientId.c_str());
}

std::string CloudSink::topicFor(const char* stream) const {
    std::string t = cfg_.topic_prefix;
    t += '/';
    t += cfg_.client_id.empty() ? "frosty-monitor" : cfg_.client_id;
    t += '/';
    t += stream;
    return t;
}

void CloudSink::maybePublish(uint32_t nowMs) {
    if (nowMs - lastPublishMs_ < cfg_.publish_interval_s * 1000UL) {
        return;
    }
    lastPublishMs_ = nowMs;

    xSemaphoreTake(aggMutex_, portMAX_DELAY);
    const bool haveChannels = channelAgg_.count() > 0;
    const bool haveBeaterVib = vibAggBeater_.count() > 0;
    const bool haveCompVib = vibAggCompressor_.count() > 0;
    xSemaphoreGive(aggMutex_);

    if (haveChannels) {
        publishChannelAggregate();
    }
    if (haveBeaterVib) {
        publishVibAggregate(vibAggBeater_);
    }
    if (haveCompVib) {
        publishVibAggregate(vibAggCompressor_);
    }
}

bool CloudSink::publishChannelAggregate() {
    xSemaphoreTake(aggMutex_, portMAX_DELAY);
    const std::string payload = channelAgg_.toJson(cfg_.publish_interval_s);
    const uint64_t ts = channelAgg_.lastTsMs();
    channelAgg_.reset();
    xSemaphoreGive(aggMutex_);

    const std::string topic = topicFor("channels");
    const bool ok = mqtt_.publish(topic.c_str(), payload.c_str());
    if (ok) {
        watermarkChannelsMs_ = ts;
        saveWatermark();
    } else {
        Serial.println("[cloud_sink] channels publish failed; this window is dropped (best-effort, SD has it)");
    }
    return ok;
}

bool CloudSink::publishVibAggregate(cloud_aggregate::VibAggregator& agg) {
    xSemaphoreTake(aggMutex_, portMAX_DELAY);
    const std::string payload = agg.toJson(cfg_.publish_interval_s);
    const uint64_t ts = agg.lastTsMs();
    agg.reset();
    xSemaphoreGive(aggMutex_);

    const std::string topic = topicFor("vibration");
    const bool ok = mqtt_.publish(topic.c_str(), payload.c_str());
    if (ok) {
        watermarkVibrationMs_ = ts; // coarse: one watermark for both pods' vibration stream
        saveWatermark();
    } else {
        Serial.println("[cloud_sink] vibration publish failed; this window is dropped (best-effort, SD has it)");
    }
    return ok;
}

bool CloudSink::publishEventNow(const Event& e) {
    if (!cfg_.enabled || state_ != State::Connected) {
        return false; // best-effort; SD (sinks[0]) already has this event durably
    }

    const std::string topic = topicFor("events");
    const std::string payload = record_format::formatEventJsonl(e.ts_unix_ms, e.type, e.detail_json);
    const bool ok = mqtt_.publish(topic.c_str(), payload.c_str());
    if (ok) {
        watermarkEventsMs_ = e.ts_unix_ms;
        saveWatermark();
    }
    return ok;
}

void CloudSink::loadWatermark() {
    xSemaphoreTake(sdSpiMutex(), portMAX_DELAY);
    File f = SD.open(kWatermarkPath, FILE_READ);
    if (!f) {
        xSemaphoreGive(sdSpiMutex());
        return; // absent is normal: first boot with cloud enabled, or no card yet
    }

    JsonDocument doc;
    const DeserializationError err = deserializeJson(doc, f);
    f.close();
    xSemaphoreGive(sdSpiMutex());

    if (err) {
        Serial.printf("[cloud_sink] %s parse error: %s; starting watermarks at 0\n", kWatermarkPath, err.c_str());
        return;
    }

    watermarkChannelsMs_ = doc["channels"] | 0ULL;
    watermarkVibrationMs_ = doc["vibration"] | 0ULL;
    watermarkEventsMs_ = doc["events"] | 0ULL;
}

void CloudSink::saveWatermark() {
    JsonDocument doc;
    doc["channels"] = watermarkChannelsMs_;
    doc["vibration"] = watermarkVibrationMs_;
    doc["events"] = watermarkEventsMs_;

    xSemaphoreTake(sdSpiMutex(), portMAX_DELAY);
    File f = SD.open(kWatermarkPath, FILE_WRITE);
    if (f) {
        serializeJson(doc, f);
        f.close();
    } else {
        Serial.printf("[cloud_sink] failed to open %s for write\n", kWatermarkPath);
    }
    xSemaphoreGive(sdSpiMutex());
}

void CloudSink::backfillFromSd() {
    // TODO(M2): replay channels_*.csv / vib_summary_*.csv / events_*.jsonl
    // rows/lines whose ts_unix_ms is older than the corresponding
    // watermark*Ms_ value above, so a device that was offline for a while
    // catches the cloud dashboard up once connectivity returns, instead of
    // only ever publishing what happens to still be live after reconnect.
    // Needs a design pass before it's implemented: how far back to look
    // (whole card? a rolling window?), how to interleave replay with live
    // publishes without either starving the other, and how to chunk a
    // backfill run across many poll() calls so it doesn't itself become a
    // long blocking operation on this task. Deliberately unimplemented for
    // M0/M1 -- this is the hook point where that lands. See
    // docs/firmware/connectivity.md (watermark / offline backfill section).
}

#else // !ARDUINO

// Non-Arduino stub: keeps this translation unit link-complete if it's ever
// pulled into a non-ESP32 build (it isn't today -- cloud_sink.cpp is not in
// [env:native]'s build_src_filter in platformio.ini, so this branch is
// belt-and-suspenders, not load-bearing). Every method is a trivial no-op /
// false, matching "disabled" behavior exactly.

CloudSink::CloudSink(const CloudConfig& cfg) : cfg_(cfg) {}
CloudSink::~CloudSink() = default;

bool CloudSink::write(const SampleRecord&) { return false; }
void CloudSink::flush() {}
bool CloudSink::isReady() const { return false; }
void CloudSink::begin() {}
void CloudSink::poll() {}

#endif // ARDUINO
