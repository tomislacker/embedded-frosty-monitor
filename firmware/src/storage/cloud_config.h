// cloud_config.h - configuration for the (optional, disabled-by-default)
// CloudSink. Deliberately Arduino-free (only <cstdint>/<string>), same
// rationale as record_types.h: config_loader.h pulls this in for AppConfig,
// and keeping it dependency-free means nothing here forces an Arduino
// toolchain just to describe the shape of the "cloud" config.json object.
//
// See docs/firmware/connectivity.md for what each field controls and the
// full config.json "cloud" object shape.
#pragma once

#include <cstdint>
#include <string>

struct CloudConfig {
    // Master switch. Defaults to false: with no "cloud" object in
    // config.json (or cloud.enabled absent/false), CloudSink does zero
    // work -- no WiFi init, isReady() is always false. This is a premium-
    // tier feature; the base product ships SD-only.
    bool enabled = false;

    std::string wifi_ssid;
    std::string wifi_pass;

    std::string mqtt_host;
    uint16_t mqtt_port = 8883; // TLS MQTT default

    // Defaults to empty; CloudSink falls back to deployment_id
    // (AppConfig::deployment_id) if this is empty, so a technician doesn't
    // have to set the same identifier twice in config.json.
    std::string client_id;

    // MQTT topics are "<topic_prefix>/<client_id>/<stream>", stream one of
    // channels|vibration|events. See connectivity.md for the exact schemas.
    std::string topic_prefix = "frostsight";

    // Cadence for the aggregated channels/vibration publishes. Events are
    // published immediately regardless of this value -- see
    // docs/firmware/connectivity.md#publish-policy.
    uint32_t publish_interval_s = 60;

    // Paths on the SD card (not the WiFi/MQTT client's own filesystem --
    // there isn't one) where the provisioning flow drops device certs. See
    // cloud/README.md (provisioning script) and connectivity.md
    // (TLS/cert provisioning flow) for how they get there.
    std::string ca_path = "/certs/ca.pem";
    std::string cert_path = "/certs/device.pem";
    std::string key_path = "/certs/device.key";
};
