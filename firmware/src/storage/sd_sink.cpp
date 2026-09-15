#include "sd_sink.h"

#include <SPI.h>
#include <cstdio>
#include <cstdlib>
#include <ctime>

#include "../pins.h"
#include "record_format.h"

namespace {

long ymdFromTsMs(uint64_t ts_unix_ms) {
    const time_t seconds = static_cast<time_t>(ts_unix_ms / 1000);
    std::tm tm_utc{};
    gmtime_r(&seconds, &tm_utc);
    return (tm_utc.tm_year + 1900) * 10000L + (tm_utc.tm_mon + 1) * 100L + tm_utc.tm_mday;
}

// RAII-ish helper: takes the shared SPI mutex on construction, releases on
// destruction, so every SD access below is guarded regardless of return path.
class SpiGuard {
public:
    SpiGuard() { xSemaphoreTake(sdSpiMutex(), portMAX_DELAY); }
    ~SpiGuard() { xSemaphoreGive(sdSpiMutex()); }
};

} // namespace

SemaphoreHandle_t sdSpiMutex() {
    static SemaphoreHandle_t mutex = xSemaphoreCreateMutex();
    return mutex;
}

SdStorageSink::~SdStorageSink() {
    closeDayFiles();
}

bool SdStorageSink::begin() {
    SpiGuard guard;
    SPI.begin(pins::SPI_SCK, pins::SPI_MISO, pins::SPI_MOSI, pins::SD_CS);
    cardPresent_ = SD.begin(pins::SD_CS, SPI);
    if (!cardPresent_) {
        Serial.println("[sd_sink] no card / mount failed; running cardless");
        return false;
    }
    if (!SD.exists("/vibration")) {
        SD.mkdir("/vibration");
    }
    Serial.println("[sd_sink] card mounted");
    return true;
}

bool SdStorageSink::isReady() const {
    return cardPresent_;
}

void SdStorageSink::closeDayFiles() {
    if (channelsFile_) channelsFile_.close();
    if (eventsFile_) eventsFile_.close();
    if (vibSummaryFile_) vibSummaryFile_.close();
    currentYmd_ = -1;
}

bool SdStorageSink::ensureDayFiles(uint64_t ts_unix_ms) {
    if (!cardPresent_) {
        return false;
    }

    const long ymd = ymdFromTsMs(ts_unix_ms);
    if (ymd == currentYmd_ && channelsFile_ && eventsFile_ && vibSummaryFile_) {
        return true;
    }

    closeDayFiles();

    char channelsPath[40];
    char eventsPath[40];
    char vibSummaryPath[48];
    std::snprintf(channelsPath, sizeof(channelsPath), "/channels_%ld.csv", ymd);
    std::snprintf(eventsPath, sizeof(eventsPath), "/events_%ld.jsonl", ymd);
    std::snprintf(vibSummaryPath, sizeof(vibSummaryPath), "/vibration/vib_summary_%ld.csv", ymd);

    const bool channelsExisted = SD.exists(channelsPath);
    const bool eventsExisted = SD.exists(eventsPath);
    const bool vibSummaryExisted = SD.exists(vibSummaryPath);

    channelsFile_ = SD.open(channelsPath, FILE_APPEND);
    eventsFile_ = SD.open(eventsPath, FILE_APPEND);
    vibSummaryFile_ = SD.open(vibSummaryPath, FILE_APPEND);

    if (!channelsFile_ || !eventsFile_ || !vibSummaryFile_) {
        Serial.println("[sd_sink] failed to open daily files");
        closeDayFiles();
        cardPresent_ = false; // card likely pulled/full; storage_writer will retry
        return false;
    }

    if (!channelsExisted) {
        channelsFile_.println(record_format::channelsCsvHeader().c_str());
    }
    if (!vibSummaryExisted) {
        vibSummaryFile_.println(record_format::vibSummaryCsvHeader().c_str());
    }
    (void)eventsExisted; // JSONL has no header

    currentYmd_ = ymd;
    return true;
}

bool SdStorageSink::writeChannelRow(const ChannelRow& row) {
    if (!channelsFile_) return false;
    channelsFile_.println(record_format::formatChannelRowCsv(row).c_str());
    return true;
}

bool SdStorageSink::writeVibSummary(const VibSummary& v) {
    if (!vibSummaryFile_) return false;
    vibSummaryFile_.println(record_format::formatVibSummaryCsv(v).c_str());
    return true;
}

bool SdStorageSink::writeEvent(const Event& e) {
    if (!eventsFile_) return false;
    eventsFile_.println(record_format::formatEventJsonl(e.ts_unix_ms, e.type, e.detail_json).c_str());
    return true;
}

bool SdStorageSink::writeVibBurst(VibBurst& burst) {
    // Ownership: per record_types.h, this function always takes ownership
    // of burst.data and must free() it before returning, success or not.
    bool ok = false;

    if (cardPresent_) {
        char path[48];
        std::snprintf(path, sizeof(path), "/vibration/vib_%u_%llu.bin",
                      static_cast<unsigned>(burst.pod_id),
                      static_cast<unsigned long long>(burst.start_ts_unix_ms));

        File f = SD.open(path, FILE_WRITE);
        if (f) {
            uint8_t header[32];
            record_format::writeVibBurstHeader(header, burst.pod_id, burst.sample_rate_hz,
                                                burst.n_samples, burst.start_ts_unix_ms,
                                                burst.scale_g_per_lsb);
            f.write(header, sizeof(header));
            if (burst.data != nullptr && burst.n_samples > 0) {
                const size_t nBytes = static_cast<size_t>(burst.n_samples) * burst.n_axes * sizeof(int16_t);
                f.write(reinterpret_cast<const uint8_t*>(burst.data), nBytes);
            }
            f.close();
            ok = true;
        } else {
            Serial.println("[sd_sink] failed to open vib burst file");
        }
    }

    std::free(burst.data);
    burst.data = nullptr;
    return ok;
}

bool SdStorageSink::write(const SampleRecord& record) {
    SpiGuard guard;

    if (!cardPresent_) {
        // Best-effort: retry mounting occasionally so a hot-inserted card
        // is picked up without a reboot. Cheap since SD.begin() no-ops
        // quickly when there's still no card.
        cardPresent_ = SD.begin(pins::SD_CS, SPI);
        if (!cardPresent_) {
            // VibBurst still owns a PSRAM/heap buffer that must be freed
            // even though we're not writing it out.
            if (record.type == RecordType::VibBurst) {
                std::free(record.vibBurst.data);
            }
            return false;
        }
    }

    switch (record.type) {
        case RecordType::ChannelRow:
            if (!ensureDayFiles(record.channel.ts_unix_ms)) return false;
            return writeChannelRow(record.channel);
        case RecordType::VibSummary:
            if (!ensureDayFiles(record.vibSummary.ts_unix_ms)) return false;
            return writeVibSummary(record.vibSummary);
        case RecordType::Event:
            if (!ensureDayFiles(record.event.ts_unix_ms)) return false;
            return writeEvent(record.event);
        case RecordType::VibBurst: {
            if (!ensureDayFiles(record.vibBurst.start_ts_unix_ms)) {
                std::free(record.vibBurst.data);
                return false;
            }
            VibBurst mutableBurst = record.vibBurst; // local copy to take ownership of data ptr
            return writeVibBurst(mutableBurst);
        }
    }
    return false;
}

void SdStorageSink::flush() {
    SpiGuard guard;
    if (channelsFile_) channelsFile_.flush();
    if (eventsFile_) eventsFile_.flush();
    if (vibSummaryFile_) vibSummaryFile_.flush();
}
