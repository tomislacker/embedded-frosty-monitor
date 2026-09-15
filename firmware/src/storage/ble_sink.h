// ble_sink.h - header-only STUB for the lower-tier "BLE walk-up offload"
// product variant. Not implemented -- isReady() always returns false and
// write()/flush() do nothing, so a BleSink instance is safe to construct and
// wire into AppContext::sinks[] (or just leave out entirely) without pulling
// in NimBLE or touching the radio.
//
// The actual design -- a GATT service exposing the on-card file list plus
// chunked file transfer, built on NimBLE-Arduino -- is documented, not
// implemented, in docs/firmware/connectivity.md (see "BLE walk-up offload").
// That doc is the thing to read before starting the real implementation;
// this header exists only so IStorageSink has a second, trivially-cheap
// concrete type to exercise the multi-sink tee in tasks/storage_writer.cpp
// today, ahead of the real BLE work landing.
//
// Deliberately avoids a NimBLE-Arduino lib_deps addition for now -- see
// connectivity.md for why (library size/build-time cost not worth paying
// before the design is actually being implemented).
#pragma once

#include "../hal/i_storage_sink.h"
#include "record_types.h"

class BleSink : public IStorageSink {
public:
    bool write(const SampleRecord& /*record*/) override { return false; }
    void flush() override {}
    bool isReady() const override { return false; }
};
