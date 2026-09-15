// i_storage_sink.h - destination for formatted records (SD card today,
// could be anything that can accept a SampleRecord later).
#pragma once

#include "../storage/record_types.h"

class IStorageSink {
public:
    virtual bool write(const SampleRecord& record) = 0;
    virtual void flush() = 0;
    virtual bool isReady() const = 0;
    virtual ~IStorageSink() = default;
};
