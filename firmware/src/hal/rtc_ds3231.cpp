#include "rtc_ds3231.h"

#include <sys/time.h>
#include <time.h>

#include <cstdio>

namespace {

// Days since the Unix epoch for a given civil (proleptic Gregorian) date.
// Timezone/DST-free by construction, from Howard Hinnant's public-domain
// chrono algorithms -- used here instead of mktime() so RTC time handling
// doesn't depend on the target's libc TZ configuration.
long daysFromCivil(int y, unsigned m, unsigned d) {
    y -= m <= 2;
    const long era = (y >= 0 ? y : y - 399) / 400;
    const unsigned yoe = static_cast<unsigned>(y - era * 400);            // [0, 399]
    const unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;  // [0, 365]
    const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;            // [0, 146096]
    return era * 146097 + static_cast<long>(doe) - 719468;
}

} // namespace

bool RtcDs3231::begin() {
    // STUB(M1): real driver would confirm I2C ack from the DS3231 here and
    // pull its time into the system clock. If the libc clock hasn't been
    // set yet (fresh boot, no RTC), seed a plausible fixed time so
    // ts_unix_ms/ts_iso in early records aren't 1970.
    struct timeval tv;
    gettimeofday(&tv, nullptr);
    if (tv.tv_sec < 1700000000) { // before ~2023-11-14, treat as "unset"
        tv.tv_sec = 1700000000;
        tv.tv_usec = 0;
        settimeofday(&tv, nullptr);
    }
    healthy_ = true;
    return true;
}

bool RtcDs3231::healthy() const {
    return healthy_;
}

const char* RtcDs3231::name() const {
    return "rtc_ds3231(stub)";
}

uint64_t RtcDs3231::now_ms() const {
    struct timeval tv;
    gettimeofday(&tv, nullptr);
    return static_cast<uint64_t>(tv.tv_sec) * 1000ULL + static_cast<uint64_t>(tv.tv_usec) / 1000ULL;
}

bool RtcDs3231::setTime(const char* iso8601) {
    if (iso8601 == nullptr) {
        return false;
    }

    int year = 0, month = 0, day = 0, hour = 0, minute = 0, second = 0;
    const int parsed = std::sscanf(iso8601, "%d-%d-%dT%d:%d:%d", &year, &month, &day, &hour, &minute, &second);
    if (parsed != 6) {
        return false;
    }
    if (month < 1 || month > 12 || day < 1 || day > 31 || hour < 0 || hour > 23 ||
        minute < 0 || minute > 59 || second < 0 || second > 60) {
        return false;
    }

    const long days = daysFromCivil(year, static_cast<unsigned>(month), static_cast<unsigned>(day));
    const long long seconds = days * 86400LL + hour * 3600LL + minute * 60LL + second;

    struct timeval tv;
    tv.tv_sec = static_cast<time_t>(seconds);
    tv.tv_usec = 0;
    if (settimeofday(&tv, nullptr) != 0) {
        return false;
    }
    return true;
}
