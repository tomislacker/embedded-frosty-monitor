// pins.h - canonical GPIO / I2C address map for frosty-monitor (ESP32-S3-DevKitC-1)
//
// This file is the single source of truth for pin assignments in firmware.
// It is mirrored (kept in sync by hand) in:
//   docs/hardware/wiring-and-pinmap.md
//   hardware/pinmap.csv
// If you change a value here, update those two documents in the same change.
#pragma once

#include <cstdint>

namespace pins {

// I2C bus (ADS1115 current sensor, DS3231 RTC, ADXL345 vibration pods)
constexpr uint8_t I2C_SDA = 8;
constexpr uint8_t I2C_SCL = 9;

// SPI bus (shared between microSD and MAX31855 thermocouple amp)
constexpr uint8_t SPI_MOSI = 11;
constexpr uint8_t SPI_SCK = 12;
constexpr uint8_t SPI_MISO = 13;

constexpr uint8_t SD_CS = 10;
constexpr uint8_t MAX31855_CS = 14;

// 1-Wire bus for DS18B20 temperature probes
constexpr uint8_t ONEWIRE_BUS = 4;

// AC-presence opto sense inputs (pulse-train, see hal/digital_input.h)
constexpr uint8_t ACSENSE_BEATER = 15;
constexpr uint8_t ACSENSE_CONTACTOR = 16;
constexpr uint8_t ACSENSE_TCC = 17;
constexpr uint8_t ACSENSE_HP = 18;

// UI
constexpr uint8_t BTN_JOURNAL = 6;
constexpr uint8_t BTN_SPARE = 7;

constexpr uint8_t LED_REC = 1;
constexpr uint8_t LED_ERR = 2;
constexpr uint8_t LED_CARD = 5;

} // namespace pins

namespace i2c_addr {

constexpr uint8_t ADS1115 = 0x48;
constexpr uint8_t DS3231 = 0x68;
constexpr uint8_t ADXL345_POD_A = 0x1D; // beater pod, ALT ADDRESS pin high
constexpr uint8_t ADXL345_POD_B = 0x53; // compressor pod, ALT ADDRESS pin low

} // namespace i2c_addr
