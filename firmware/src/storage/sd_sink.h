// sd_sink.h - IStorageSink backed by a microSD card on the shared SPI bus.
//
// The pipeline must run cardless on a bare devkit: if no card is present
// (or mounting fails), begin()/isReady() report false, write() logs to
// Serial and returns false without touching the filesystem, and nothing
// crashes. storage_writer keeps consuming its queue either way so records
// just aren't persisted until a card shows up (isReady() is re-checked on
// each write, so hot-inserting a card recovers automatically).
#pragma once

#include <FS.h>
#include <SD.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

#include "../hal/i_storage_sink.h"
#include "record_types.h"

// Shared SPI-bus mutex: microSD (SD.h, this file) and the MAX31855
// thermocouple amp (hal/temp_thermocouple_max31855, real impl at M1) live
// on the same SPI bus (pins::SPI_MOSI/SCK/MISO) with separate CS lines.
// Anything doing an SPI transaction on that bus must hold this mutex for
// the duration of the transaction. Lazily created on first call (expected
// to happen during single-threaded setup()).
SemaphoreHandle_t sdSpiMutex();

class SdStorageSink : public IStorageSink {
public:
    SdStorageSink() = default;
    ~SdStorageSink() override;

    // Attempts to mount the card. Safe to call even if no card is present;
    // returns the same thing isReady() will subsequently return.
    bool begin();

    bool write(const SampleRecord& record) override;
    void flush() override;
    bool isReady() const override;

private:
    bool cardPresent_ = false;
    long currentYmd_ = -1; // YYYYMMDD of currently-open daily files, -1 = none

    File channelsFile_;
    File eventsFile_;
    File vibSummaryFile_;

    bool ensureDayFiles(uint64_t ts_unix_ms);
    void closeDayFiles();

    bool writeChannelRow(const ChannelRow& row);
    bool writeVibSummary(const VibSummary& v);
    bool writeEvent(const Event& e);
    // Writes the .bin burst file and, per record_types.h VibBurst ownership
    // contract, frees burst.data once done (success or failure).
    bool writeVibBurst(VibBurst& burst);
};
