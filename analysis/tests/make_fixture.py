"""Deterministically regenerate `tests/fixtures/sample_deployment/`.

Run from anywhere (paths are relative to this file):

    python tests/make_fixture.py

Builds a small, synthetic but format-correct card dump per
`docs/firmware/data-format-spec.md`: two daily channel CSVs (~600 rows
each, 1Hz), one events JSONL, a vibration summary CSV, and two raw
vibration burst `.bin` files. Everything is seeded
(`np.random.default_rng(42)`) so re-running reproduces byte-identical
output.
"""

from __future__ import annotations

import json
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample_deployment"

DEPLOYMENT_ID = "fixture-dep-001"
MACHINE_MODEL = "137A"
MACHINE_SERIAL = "SN-FIXTURE-0001"
TECHNICIAN = "test-tech"
FIRMWARE_VERSION = "0.1.0-fixture"

DAY_1 = datetime(2026, 6, 1, tzinfo=timezone.utc)
DAY_2 = datetime(2026, 6, 2, tzinfo=timezone.utc)
ROWS_PER_DAY = 600  # ~10 minutes at 1Hz

CHANNELS_HEADER = [
    "ts_iso",
    "ts_unix_ms",
    "current_beater_a",
    "current_compressor_a",
    "temp_cylinder_c",
    "temp_cond_in_c",
    "temp_cond_out_c",
    "temp_ambient_c",
    "temp_hopper_c",
    "temp_discharge_c",
    "beater_on",
    "compressor_cmd",
    "tcc_satisfied",
    "hp_ok",
]

VIB_SUMMARY_HEADER = [
    "ts_iso",
    "ts_unix_ms",
    "pod_id",
    "rms_x_g",
    "rms_y_g",
    "rms_z_g",
    "peak_x_g",
    "peak_y_g",
    "peak_z_g",
    "band_low_g2",
    "band_mid_g2",
    "band_high_g2",
]

BURST_HEADER_FORMAT = "<4sBBHIIB3sQf"
BURST_SAMPLE_RATE_HZ = 1600
BURST_DURATION_S = 0.5
BURST_N_SAMPLES = int(BURST_SAMPLE_RATE_HZ * BURST_DURATION_S)  # 800
BURST_SCALE_G_PER_LSB = 0.004


def _iso(ts: datetime) -> str:
    return ts.isoformat().replace("+00:00", "Z")


def _unix_ms(ts: datetime) -> int:
    return int(ts.timestamp() * 1000)


def build_channels_day(rng: np.random.Generator, day_start: datetime) -> pd.DataFrame:
    n = ROWS_PER_DAY
    timestamps = [day_start + timedelta(seconds=i) for i in range(n)]
    t = np.arange(n)

    # Compressor duty-cycles with a ~5 minute (300s) period, ~50% duty.
    cycle_period_s = 300
    compressor_cmd = ((t % cycle_period_s) < (cycle_period_s // 2)).astype(int)

    # Beater runs most of the time, with one short pause mid-run.
    beater_on = np.ones(n, dtype=int)
    pause_start = n // 2
    pause_len = min(20, n // 10)
    beater_on[pause_start : pause_start + pause_len] = 0

    current_beater_a = np.where(
        beater_on == 1,
        3.0 + rng.normal(0, 0.15, n),
        0.05 + rng.normal(0, 0.01, n).clip(min=0),
    )

    compressor_base = np.where(compressor_cmd == 1, 7.0, 0.0)
    current_compressor_a = compressor_base + np.where(
        compressor_cmd == 1, rng.normal(0, 0.2, n), rng.normal(0, 0.02, n)
    )
    current_compressor_a = current_compressor_a.clip(min=0)

    # Cylinder cools while compressor runs, drifts back up while off.
    temp_cylinder_c = np.empty(n)
    temp_cylinder_c[0] = 4.0
    for i in range(1, n):
        drift = -0.03 if compressor_cmd[i] else 0.02
        temp_cylinder_c[i] = temp_cylinder_c[i - 1] + drift + rng.normal(0, 0.05)

    temp_ambient_c = 22.0 + rng.normal(0, 0.3, n)
    temp_cond_in_c = temp_ambient_c + rng.normal(0, 0.2, n)
    temp_cond_out_c = np.where(
        compressor_cmd == 1,
        temp_cond_in_c + 12.0 + rng.normal(0, 0.5, n),
        temp_cond_in_c + rng.normal(0, 0.2, n),
    )
    temp_discharge_c = np.where(
        compressor_cmd == 1,
        70.0 + rng.normal(0, 2.0, n),
        30.0 + rng.normal(0, 1.0, n),
    )

    # TCC satisfies once the cylinder gets cold enough near the end of a
    # freeze-down; high-pressure switch reads OK throughout.
    tcc_satisfied = (temp_cylinder_c < -2.0).astype(int)
    hp_ok = np.ones(n, dtype=int)

    df = pd.DataFrame(
        {
            "ts_iso": [_iso(ts) for ts in timestamps],
            "ts_unix_ms": [_unix_ms(ts) for ts in timestamps],
            "current_beater_a": current_beater_a,
            "current_compressor_a": current_compressor_a,
            "temp_cylinder_c": temp_cylinder_c,
            "temp_cond_in_c": temp_cond_in_c,
            "temp_cond_out_c": temp_cond_out_c,
            "temp_ambient_c": temp_ambient_c,
            "temp_hopper_c": np.nan,  # hopper probe not wired on this fixture
            "temp_discharge_c": temp_discharge_c,
            "beater_on": beater_on,
            "compressor_cmd": compressor_cmd,
            "tcc_satisfied": tcc_satisfied,
            "hp_ok": hp_ok,
        },
        columns=CHANNELS_HEADER,
    )

    # A handful of dropped discharge-thermocouple samples, to exercise NaN
    # handling beyond the fully-empty hopper column.
    drop_idx = rng.choice(n, size=max(1, n // 150), replace=False)
    df.loc[drop_idx, "temp_discharge_c"] = np.nan

    return df


def write_channels(rng: np.random.Generator) -> None:
    for day_start in (DAY_1, DAY_2):
        df = build_channels_day(rng, day_start)
        out_path = FIXTURE_DIR / f"channels_{day_start:%Y%m%d}.csv"
        # Fixed 3-decimal precision keeps the checked-in fixture small
        # without losing anything the tests or plots care about.
        df.to_csv(out_path, index=False, float_format="%.3f")


def write_events() -> None:
    events = [
        {
            "ts_iso": _iso(DAY_1),
            "ts_unix_ms": _unix_ms(DAY_1),
            "type": "system",
            "detail": {"msg": "boot", "firmware_version": FIRMWARE_VERSION},
        },
        {
            "ts_iso": _iso(DAY_1 + timedelta(seconds=5)),
            "ts_unix_ms": _unix_ms(DAY_1 + timedelta(seconds=5)),
            "type": "system",
            "detail": {"msg": "config loaded"},
        },
        {
            "ts_iso": _iso(DAY_1 + timedelta(seconds=120)),
            "ts_unix_ms": _unix_ms(DAY_1 + timedelta(seconds=120)),
            "type": "button",
            "detail": {"button": "event_journal", "note": "tech observed rattling"},
        },
        {
            "ts_iso": _iso(DAY_1 + timedelta(seconds=180)),
            "ts_unix_ms": _unix_ms(DAY_1 + timedelta(seconds=180)),
            "type": "trigger",
            "detail": {"reason": "current_spike", "channel": "current_compressor_a"},
        },
        {
            "ts_iso": _iso(DAY_1 + timedelta(seconds=540)),
            "ts_unix_ms": _unix_ms(DAY_1 + timedelta(seconds=540)),
            "type": "system",
            "detail": {"msg": "channels_20260602.csv rotation pending"},
        },
    ]
    out_path = FIXTURE_DIR / f"events_{DAY_1:%Y%m%d}.jsonl"
    with open(out_path, "w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event) + "\n")


def _make_burst_samples(rng: np.random.Generator, freq_hz: float) -> np.ndarray:
    t = np.arange(BURST_N_SAMPLES) / BURST_SAMPLE_RATE_HZ
    x = 0.05 * np.sin(2 * np.pi * freq_hz * t) + rng.normal(0, 0.01, BURST_N_SAMPLES)
    y = 0.03 * np.sin(2 * np.pi * (freq_hz * 1.7) * t + 0.4) + rng.normal(
        0, 0.01, BURST_N_SAMPLES
    )
    z = 1.0 + 0.02 * np.sin(2 * np.pi * (freq_hz * 0.5) * t) + rng.normal(
        0, 0.005, BURST_N_SAMPLES
    )  # z carries ~1g gravity offset
    return np.stack([x, y, z], axis=1)


def write_burst(rng: np.random.Generator, pod_id: int, start_ts: datetime, freq_hz: float) -> Path:
    vib_dir = FIXTURE_DIR / "vibration"
    samples_g = _make_burst_samples(rng, freq_hz)
    int16_samples = np.round(samples_g / BURST_SCALE_G_PER_LSB).astype(np.int16)

    header = struct.pack(
        BURST_HEADER_FORMAT,
        b"FVB1",
        1,  # format_version
        pod_id,
        0,  # reserved
        BURST_SAMPLE_RATE_HZ,
        BURST_N_SAMPLES,
        3,  # n_axes
        b"\x00\x00\x00",
        _unix_ms(start_ts),
        BURST_SCALE_G_PER_LSB,
    )

    ts_ms = _unix_ms(start_ts)
    out_path = vib_dir / f"vib_{pod_id}_{ts_ms}.bin"
    with open(out_path, "wb") as fh:
        fh.write(header)
        fh.write(int16_samples.tobytes())
    return out_path


def write_vibration(rng: np.random.Generator) -> None:
    vib_dir = FIXTURE_DIR / "vibration"
    vib_dir.mkdir(parents=True, exist_ok=True)

    n_rows = 20
    interval_s = (ROWS_PER_DAY // n_rows) or 1
    burst_row_indices = {5: (1, 40.0), 12: (2, 90.0)}  # row idx -> (pod_id, freq_hz)

    rows = []
    for i in range(n_rows):
        ts = DAY_1 + timedelta(seconds=i * interval_s)
        pod_id, freq_hz = burst_row_indices.get(i, (1 if i % 2 == 0 else 2, 30.0))
        samples_g = _make_burst_samples(rng, freq_hz)

        rms = np.sqrt(np.mean(samples_g**2, axis=0))
        peak = np.max(np.abs(samples_g), axis=0)
        # Coarse synthetic band-energy split, not a real FFT — good enough
        # for a fixture meant to exercise the loader/plots, not the DSP.
        band_low = float(np.var(samples_g[:, 2]) * 0.5)
        band_mid = float(np.var(samples_g[:, 0]) * 0.8)
        band_high = float(np.var(samples_g[:, 1]) * 0.3)

        rows.append(
            {
                "ts_iso": _iso(ts),
                "ts_unix_ms": _unix_ms(ts),
                "pod_id": pod_id,
                "rms_x_g": rms[0],
                "rms_y_g": rms[1],
                "rms_z_g": rms[2],
                "peak_x_g": peak[0],
                "peak_y_g": peak[1],
                "peak_z_g": peak[2],
                "band_low_g2": band_low,
                "band_mid_g2": band_mid,
                "band_high_g2": band_high,
            }
        )

        if i in burst_row_indices:
            write_burst(rng, pod_id, ts, freq_hz)

    df = pd.DataFrame(rows, columns=VIB_SUMMARY_HEADER)
    out_path = vib_dir / f"vib_summary_{DAY_1:%Y%m%d}.csv"
    df.to_csv(out_path, index=False, float_format="%.5f")


def write_manifest() -> None:
    manifest = {
        "schema_version": 1,
        "deployment_id": DEPLOYMENT_ID,
        "machine_model": MACHINE_MODEL,
        "machine_serial": MACHINE_SERIAL,
        "technician": TECHNICIAN,
        "firmware_version": FIRMWARE_VERSION,
        "start_ts_iso": _iso(DAY_1),
        "channel_map": {
            "current_beater_a": {"location": "beater motor leg", "calibration": "30A/1V CT"},
            "current_compressor_a": {
                "location": "compressor contactor leg",
                "calibration": "30A/1V CT",
            },
            "temp_cylinder_c": {
                "location": "freezing cylinder jacket",
                "calibration": "DS18B20 28-000000fixture1",
            },
            "temp_cond_in_c": {
                "location": "condenser air intake",
                "calibration": "DS18B20 28-000000fixture2",
            },
            "temp_cond_out_c": {
                "location": "condenser air discharge",
                "calibration": "DS18B20 28-000000fixture3",
            },
            "temp_ambient_c": {
                "location": "compartment ambient",
                "calibration": "DS18B20 28-000000fixture4",
            },
            "temp_hopper_c": {"location": "hopper (not wired)", "calibration": "n/a"},
            "temp_discharge_c": {
                "location": "compressor discharge line",
                "calibration": "MAX31855, cold-junction offset 0.0",
            },
            "vib_pod_1": {"location": "beater-drive housing", "calibration": "0.004 g/LSB"},
            "vib_pod_2": {"location": "compressor mount", "calibration": "0.004 g/LSB"},
        },
        "config_effective": {
            "sample_rates": {"channels_hz": 1, "vibration_hz": BURST_SAMPLE_RATE_HZ},
            "burst_settings": {
                "duration_s": BURST_DURATION_S,
                "n_axes": 3,
                "periodic_interval_s": interval_seconds_between_bursts(),
            },
        },
    }
    with open(FIXTURE_DIR / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")


def interval_seconds_between_bursts() -> int:
    return (ROWS_PER_DAY // 20) or 1


def write_config() -> None:
    config = {
        "deployment_id": DEPLOYMENT_ID,
        "machine_serial": MACHINE_SERIAL,
        "technician": TECHNICIAN,
    }
    with open(FIXTURE_DIR / "config.json", "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)
        fh.write("\n")


def main() -> None:
    rng = np.random.default_rng(SEED)
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    write_manifest()
    write_config()
    write_channels(rng)
    write_events()
    write_vibration(rng)

    print(f"Wrote fixture to {FIXTURE_DIR}")


if __name__ == "__main__":
    main()
