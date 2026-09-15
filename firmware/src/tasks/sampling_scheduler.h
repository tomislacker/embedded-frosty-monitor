// sampling_scheduler.h - 1Hz task: reads every HAL channel, assembles a
// ChannelRow, and enqueues it for storage_writer. Also watches current
// draw for a simple spike heuristic that nudges vibration_capture into an
// out-of-cycle burst.
#pragma once

#include "../app_context.h"

// Creates and starts the sampling scheduler FreeRTOS task. `ctx` must
// outlive the task (it's owned for the process lifetime by main.cpp).
void startSamplingSchedulerTask(AppContext* ctx);
