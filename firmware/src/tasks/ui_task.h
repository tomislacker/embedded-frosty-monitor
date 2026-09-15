// ui_task.h - debounces the 2 front-panel buttons and drives the 3 status
// LEDs. Journal button press enqueues an Event record; spare button is
// wired/debounced but unmapped (STUB(M1): assign an action).
#pragma once

#include "../app_context.h"

void startUiTask(AppContext* ctx);
