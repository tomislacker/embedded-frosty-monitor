// cloud_sink.h - IStorageSink that best-effort mirrors records to an MQTT
// broker over TLS WiFi, for the premium "real-time remote monitoring" tier.
//
// DISABLED BY DEFAULT (CloudConfig::enabled == false, the config.json
// default -- see cloud_config.h). When disabled: begin() does not touch
// WiFi at all, isReady() is always false, write()/flush()/poll() are cheap
// no-ops. SD (SdStorageSink) remains the source of truth in every case --
// this sink publishes best-effort and its failure must never affect SD
// writes; see tasks/storage_writer.cpp for how the two are teed together.
//
// The WiFi/TLS/MQTT bits below only make sense on-target, so the whole
// implementation is guarded with #ifdef ARDUINO; the aggregation math this
// class drives (mean/min/max accumulation, JSON serialization) lives in the
// Arduino-free storage/cloud_aggregate.{h,cpp} instead, which IS native
// unit tested. This header is not part of the native build_src_filter
// (see platformio.ini), so in practice the guard is a belt-and-suspenders
// documentation aid, not something that's ever exercised in the [env:native]
// build today.
//
// See docs/firmware/connectivity.md for the full design: the state machine
// below, publish topics/schemas, TLS cert provisioning, and the
// watermark/backfill (M2) plan.
#pragma once

#include "../hal/i_storage_sink.h"
#include "cloud_aggregate.h"
#include "cloud_config.h"
#include "record_types.h"

#ifdef ARDUINO
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#endif

class CloudSink : public IStorageSink {
public:
    explicit CloudSink(const CloudConfig& cfg);
    ~CloudSink() override;

    // IStorageSink
    bool write(const SampleRecord& record) override;
    void flush() override; // see .cpp: intentionally a no-op, and why
    bool isReady() const override;

    // Starts the sink. No-op (no WiFi/MQTT touched at all) if
    // cfg.enabled == false. Safe to call exactly once, from main.cpp
    // alongside every other HAL/sink begin() call.
    //
    // When enabled, spawns a dedicated low-priority background FreeRTOS
    // task that drives poll() in a loop. This is deliberately NOT pumped
    // inline from StorageWriterTask: PubSubClient's connect()/publish()
    // calls are blocking (a TCP+TLS handshake can take seconds on a bad
    // link), and StorageWriterTask must never stall -- SD is the source of
    // truth and its write/flush cadence is the direct knob on power-loss
    // data exposure (see docs/firmware/architecture.md#power-loss-resilience).
    // Isolating the blocking work onto its own low-priority task means a
    // wedged cloud connection costs nothing but that task's own progress.
    void begin();

    // Non-blocking-per-call connection/publish state machine step; see
    // docs/firmware/connectivity.md#cloudsink-state-machine for the state
    // diagram. Public mainly so it's unit-testable/callable directly if
    // begin()'s background task is ever replaced with something else (e.g.
    // pumped from a scheduler); normal operation never needs to call this
    // directly, begin() already wires up the background task.
    void poll();

private:
    CloudConfig cfg_;

#ifdef ARDUINO
    enum class State {
        Idle,           // not yet attempted / backoff elapsed, about to retry
        WifiConnecting,
        WifiConnected,
        MqttConnecting,
        Connected,
        Backoff,        // waiting out backoffMs_ before the next Idle retry
    };

    State state_ = State::Idle;
    uint32_t stateEnteredMs_ = 0;
    uint32_t backoffMs_ = kBackoffInitialMs;
    bool started_ = false;

    bool certsLoaded_ = false;
    std::string caCert_;
    std::string clientCert_;
    std::string clientKey_;

    WiFiClientSecure tlsClient_;
    PubSubClient mqtt_;

    // Guards the three aggregators below: write() runs on StorageWriterTask,
    // poll()'s publish path runs on the background cloud task. Both are
    // quick (accumulate a handful of floats, or serialize/reset), so this is
    // held only very briefly, never across network I/O.
    SemaphoreHandle_t aggMutex_ = nullptr;

    cloud_aggregate::ChannelAggregator channelAgg_;
    cloud_aggregate::VibAggregator vibAggBeater_;
    cloud_aggregate::VibAggregator vibAggCompressor_;
    uint32_t lastPublishMs_ = 0;

    // Last-published-ts-per-stream, mirrored to /cloud_watermark.json on
    // every successful publish. See docs/firmware/connectivity.md#watermark
    // -- offline backfill using this watermark is TODO(M2), not implemented
    // (backfillFromSd() below is the stubbed hook).
    uint64_t watermarkChannelsMs_ = 0;
    uint64_t watermarkVibrationMs_ = 0;
    uint64_t watermarkEventsMs_ = 0;

    static constexpr uint32_t kWifiConnectTimeoutMs = 15000;
    static constexpr uint32_t kMqttConnectTimeoutMs = 10000;
    static constexpr uint32_t kBackoffInitialMs = 2000;
    static constexpr uint32_t kBackoffMaxMs = 5 * 60 * 1000; // cap at 5 min

    void enterState(State s);
    void enterBackoff();
    bool loadCertsFromSd();
    bool beginMqttConnect();
    void maybePublish(uint32_t nowMs);
    bool publishChannelAggregate();
    bool publishVibAggregate(cloud_aggregate::VibAggregator& agg);
    bool publishEventNow(const Event& e);
    std::string topicFor(const char* stream) const;

    void loadWatermark();
    void saveWatermark();

    // TODO(M2): replay SD files older than the relevant watermark once a
    // stable MQTT connection is established after a period offline. Not
    // implemented in M0/M1 -- deliberately stubbed (see .cpp) so the hook
    // point exists without committing to a replay design (chunking, ordering
    // vs. live records, how far back to look) before it's needed.
    void backfillFromSd();
#endif
};
