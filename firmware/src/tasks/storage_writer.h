// storage_writer.h - single consumer of the sample queue. Formatting per
// the on-disk data format happens inside IStorageSink (sd_sink calls
// storage/record_format), this task is just the queue drain + periodic
// flush loop. Kept as the ONLY task that touches the sink so SD access
// never needs cross-task locking beyond the shared SPI-bus mutex.
#pragma once

#include "../app_context.h"

void startStorageWriterTask(AppContext* ctx);
