// vibration_capture.h - periodic (config-driven, default 300s / 15s in
// FROSTY_DEV_MODE) vibration burst capture for each accelerometer pod.
//
// Captures a short burst into a PSRAM buffer, computes summary stats, and
// enqueues a VibSummary every cycle plus a VibBurst (raw binary) every few
// cycles (or immediately on a sampling_scheduler current-spike trigger) so
// the SD card isn't flooded with raw binaries on every capture.
#pragma once

#include "../app_context.h"

void startVibrationCaptureTask(AppContext* ctx);
