"""Seeded generator for a realistic 14-day frosty-monitor demo deployment.

Writes a spec-compliant deployment directory (see
`docs/firmware/data-format-spec.md`: `manifest.json`, `config.json`, one
`channels_YYYYMMDD.csv` + `events_YYYYMMDD.jsonl` per day, and
`vibration/vib_summary_YYYYMMDD.csv` + a handful of raw
`vibration/vib_<pod>_<ts>.bin` bursts) representing a plausible 137A bar
soft-serve/shake machine over 14 days ending 2026-09-01.

The data is otherwise healthy *except* for a deliberately injected
diagnostic story, used to exercise `frosty_analysis.report` end to end:

  (a) From day 6 onward, compressor on-cycle durations progressively
      shorten, clustered in the warm afternoon hours (13:00-18:00), down to
      well under 60s by the end of the window — a refrigerant-loss
      short-cycling signature — with condenser delta-T falling in step
      (down to ~60% of healthy during the worst cycles).
  (b) Day 9, evening: a knocking episode — a sharp beater-pod (pod 1)
      vibration spike with a strong low-frequency raw-burst component,
      a "trigger" auto-capture event, and a staff "button" journal entry
      ~2.5 minutes later.
  (c) Condenser air-intake temperature drifts slowly upward across the
      whole window (an airflow-degradation hint).

Output is written OUTSIDE the repo by default (~100MB+ at 1Hz over 14 days)
so it is never committed; only this script is. Generation streams one day
of channels/vibration data to disk at a time to stay memory-sane.

Run:

    python -m frosty_analysis.report --help   # (report generator)
    python analysis/scripts/make_demo_deployment.py [--out-dir DIR] [--seed N]
"""

from __future__ import annotations

import argparse
import json
import struct
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 7
N_DAYS = 14
END_DATE = datetime(2026, 9, 1, tzinfo=timezone.utc)
START_DATE = END_DATE - timedelta(days=N_DAYS - 1)
SECONDS_PER_DAY = 86400

DEPLOYMENT_ID = "demo-neighborhood-cantina-137a"
MACHINE_MODEL = "137A"
MACHINE_SERIAL = "SN-DEMO-137A-0042"
TECHNICIAN = "field-tech-demo"
FIRMWARE_VERSION = "1.4.2"

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

VIB_INTERVAL_S = 300  # periodic vibration-summary capture cadence
DEGRADATION_START_DAY = 6  # 0-indexed: day 6 = the 7th day of the deployment
WARM_AFTERNOON_START_HOUR = 13
WARM_AFTERNOON_END_HOUR = 18
KNOCK_DAY_INDEX = 9
KNOCK_OFFSET_S = 21 * 3600 + 15 * 60  # 21:15 local-to-UTC-treated offset into the day
KNOCK_BUTTON_DELAY_S = 150  # staff notices and logs it 2.5 minutes later
ROUTINE_BURST_EVERY_N_DAYS = 2
ROUTINE_BURST_HOUR = 10


def _iso(ts: datetime) -> str:
    return ts.isoformat().replace("+00:00", "Z")


def _unix_ms(ts: datetime) -> int:
    return int(ts.timestamp() * 1000)


# --------------------------------------------------------------------------
# per-day channel simulation
# --------------------------------------------------------------------------


def _build_compressor_segments(rng: np.random.Generator, day_index: int, n: int):
    """Build the day's compressor on/off schedule as contiguous segments.

    Returns `(compressor_cmd, dt_factor, segments)`:
      - `compressor_cmd`: int array, 1 while the compressor is commanded on.
      - `dt_factor`: float array, condenser delta-T multiplier in effect at
        each second (1.0 healthy, down to 0.6 during the worst degraded
        short cycles).
      - `segments`: list of `(start, end, state)` covering the whole day,
        used to drive the cylinder-temperature relaxation model.
    """
    compressor_cmd = np.zeros(n, dtype=np.int64)
    dt_factor = np.ones(n, dtype=np.float64)
    segments: list[tuple[int, int, int]] = []

    degradation = 0.0
    if day_index >= DEGRADATION_START_DAY:
        degradation = min(1.0, (day_index - DEGRADATION_START_DAY) / 7.0)

    t = 0
    state = 1  # start "on" (freeze-down) for variety across days
    while t < n:
        hour = (t // 3600) % 24
        warm_afternoon = WARM_AFTERNOON_START_HOUR <= hour < WARM_AFTERNOON_END_HOUR
        degraded = degradation > 0 and warm_afternoon

        if state == 1:
            if degraded:
                center_on = 150.0 - 120.0 * degradation  # 150s at onset -> 30s at worst
                dur = float(np.clip(rng.normal(center_on, 12.0), 10.0, 200.0))
                factor = 1.0 - 0.4 * degradation
            else:
                dur = float(np.clip(rng.normal(330.0, 55.0), 240.0, 480.0))  # 4-8 min healthy
                factor = 1.0
            dur_i = int(round(dur))
            end = min(t + dur_i, n)
            compressor_cmd[t:end] = 1
            dt_factor[t:end] = factor
            segments.append((t, end, 1))
        else:
            if degraded:
                center_off = 200.0 - 150.0 * degradation  # rapid re-trigger when degraded
                dur = float(np.clip(rng.normal(center_off, 25.0), 20.0, 220.0))
            else:
                dur = float(np.clip(rng.normal(260.0, 45.0), 120.0, 420.0))
            dur_i = int(round(dur))
            end = min(t + dur_i, n)
            segments.append((t, end, 0))

        t = end
        state = 1 - state

    return compressor_cmd, dt_factor, segments


def _build_beater_on(rng: np.random.Generator, day_index: int, day_start: datetime, n: int) -> np.ndarray:
    """Order-driven beater usage during business hours (11:00-02:00 next day).

    Busier (shorter order interarrival) on Friday/Saturday nights.
    """
    beater_on = np.zeros(n, dtype=np.int64)
    weekday = day_start.weekday()
    is_busy_night = weekday in (4, 5)  # Fri, Sat
    mean_gap = 45.0 if is_busy_night else 100.0

    t = 0
    while t < n:
        hour = (t // 3600) % 24
        open_now = hour >= 11 or hour < 2
        if not open_now:
            # jump to the next open second rather than stepping one at a time
            if hour < 11:
                t = 11 * 3600
            else:
                t = n  # past 02:00 and before 11:00 next occurrence handled by next day
            continue
        gap = max(5, int(rng.exponential(mean_gap)))
        t += gap
        if t >= n:
            break
        hour = (t // 3600) % 24
        if not (hour >= 11 or hour < 2):
            continue
        run_len = int(np.clip(rng.normal(35.0, 12.0), 10.0, 90.0))
        end = min(t + run_len, n)
        beater_on[t:end] = 1
        t = end

    return beater_on


def _relax_cylinder_temp(
    rng: np.random.Generator,
    segments: list[tuple[int, int, int]],
    temp0: float,
    n: int,
    target_on: float = -6.0,
    target_off: float = 1.0,
    k: float = 0.01,
    noise_sd: float = 0.06,
) -> np.ndarray:
    """Exponential relaxation toward a per-state target, computed analytically
    per contiguous on/off segment (bounded, unlike a raw cumulative-sum
    integrator, so it stays stable across a 14-day/1.2M-sample deployment).
    """
    temp = np.empty(n, dtype=np.float64)
    current = temp0
    for start, end, state in segments:
        length = end - start
        if length <= 0:
            continue
        target = target_on if state == 1 else target_off
        idx = np.arange(length)
        base = target + (current - target) * np.exp(-k * idx)
        seg = base + rng.normal(0, noise_sd, length)
        temp[start:end] = seg
        current = seg[-1]
    return temp


def build_channels_day(
    rng: np.random.Generator, day_index: int, day_start: datetime, carry: dict
) -> pd.DataFrame:
    n = SECONDS_PER_DAY
    t = np.arange(n)
    timestamps = [day_start + timedelta(seconds=int(i)) for i in range(n)]
    hour_frac = t / 3600.0

    compressor_cmd, dt_factor, segments = _build_compressor_segments(rng, day_index, n)
    beater_on = _build_beater_on(rng, day_index, day_start, n)

    current_beater_a = np.where(
        beater_on == 1,
        3.0 + rng.normal(0, 0.15, n),
        0.05 + np.abs(rng.normal(0, 0.01, n)),
    )
    current_compressor_a = np.where(
        compressor_cmd == 1,
        7.0 + rng.normal(0, 0.2, n),
        np.abs(rng.normal(0, 0.02, n)),
    )

    temp0 = carry.get("temp_cylinder", 4.0)
    temp_cylinder_c = _relax_cylinder_temp(rng, segments, temp0, n)
    carry["temp_cylinder"] = float(temp_cylinder_c[-1])

    # Ambient/condenser intake: diurnal swing (afternoon peak) plus a slow
    # upward drift across the deployment window (airflow-degradation hint).
    diurnal = 3.0 * np.sin(2 * np.pi * (hour_frac - 15.0) / 24.0)
    drift = 0.16 * day_index
    ambient_base = 23.0 + diurnal + drift
    temp_cond_in_c = ambient_base + rng.normal(0, 0.25, n)
    temp_ambient_c = ambient_base - 1.0 + rng.normal(0, 0.3, n)
    temp_hopper_c = 0.4 * temp_cylinder_c + 0.5 * temp_ambient_c + 1.0 + rng.normal(0, 0.3, n)

    temp_cond_out_c = np.where(
        compressor_cmd == 1,
        temp_cond_in_c + 12.0 * dt_factor + rng.normal(0, 0.5, n),
        temp_cond_in_c + rng.normal(0, 0.2, n),
    )
    temp_discharge_c = np.where(
        compressor_cmd == 1,
        70.0 + 15.0 * (1.0 - dt_factor) + rng.normal(0, 2.0, n),
        30.0 + rng.normal(0, 1.0, n),
    )

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
            "temp_hopper_c": temp_hopper_c,
            "temp_discharge_c": temp_discharge_c,
            "beater_on": beater_on,
            "compressor_cmd": compressor_cmd,
            "tcc_satisfied": tcc_satisfied,
            "hp_ok": hp_ok,
        },
        columns=CHANNELS_HEADER,
    )

    # A handful of dropped discharge-thermocouple samples, same flavor as
    # the small test fixture.
    drop_idx = rng.choice(n, size=max(1, n // 4000), replace=False)
    df.loc[drop_idx, "temp_discharge_c"] = np.nan

    return df, beater_on, compressor_cmd


# --------------------------------------------------------------------------
# vibration
# --------------------------------------------------------------------------


def _make_burst_samples(
    rng: np.random.Generator,
    freq_hz: float,
    amplitude_g: float = 0.05,
    z_gravity_g: float = 1.0,
) -> np.ndarray:
    t = np.arange(BURST_N_SAMPLES) / BURST_SAMPLE_RATE_HZ
    x = amplitude_g * np.sin(2 * np.pi * freq_hz * t) + rng.normal(0, 0.01, BURST_N_SAMPLES)
    y = amplitude_g * 0.6 * np.sin(2 * np.pi * (freq_hz * 1.7) * t + 0.4) + rng.normal(
        0, 0.01, BURST_N_SAMPLES
    )
    z = z_gravity_g + amplitude_g * 0.4 * np.sin(2 * np.pi * (freq_hz * 0.5) * t) + rng.normal(
        0, 0.005, BURST_N_SAMPLES
    )
    return np.stack([x, y, z], axis=1)


def write_burst(
    rng: np.random.Generator,
    vib_dir: Path,
    pod_id: int,
    start_ts: datetime,
    freq_hz: float,
    amplitude_g: float = 0.05,
) -> Path:
    samples_g = _make_burst_samples(rng, freq_hz, amplitude_g=amplitude_g)
    int16_samples = np.round(samples_g / BURST_SCALE_G_PER_LSB).astype(np.int16)

    header = struct.pack(
        BURST_HEADER_FORMAT,
        b"FVB1",
        1,
        pod_id,
        0,
        BURST_SAMPLE_RATE_HZ,
        BURST_N_SAMPLES,
        3,
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


def build_vib_summary_day(
    rng: np.random.Generator,
    day_index: int,
    day_start: datetime,
    beater_on: np.ndarray,
    compressor_cmd: np.ndarray,
    vib_dir: Path,
) -> pd.DataFrame:
    n_per_day = SECONDS_PER_DAY // VIB_INTERVAL_S
    rows = []

    for pod_id in (1, 2):
        for i in range(n_per_day):
            offset = i * VIB_INTERVAL_S
            ts = day_start + timedelta(seconds=offset)
            if pod_id == 1:
                active = beater_on[offset] == 1
                base_xy, base_z = (0.07, 1.02) if active else (0.02, 1.0)
            else:
                active = compressor_cmd[offset] == 1
                base_xy, base_z = (0.05, 1.01) if active else (0.015, 1.0)

            rms_x = abs(base_xy + rng.normal(0, 0.005))
            rms_y = abs(base_xy * 0.9 + rng.normal(0, 0.005))
            rms_z = abs(base_z + rng.normal(0, 0.01))
            peak_x = rms_x * rng.uniform(2.5, 3.5)
            peak_y = rms_y * rng.uniform(2.5, 3.5)
            peak_z = rms_z * rng.uniform(1.05, 1.3)
            band_low = (rms_x**2) * rng.uniform(0.3, 0.5)
            band_mid = (rms_y**2) * rng.uniform(0.5, 0.8)
            band_high = max(rms_z**2 - base_z**2, 1e-6) * rng.uniform(0.4, 0.9)

            rows.append(
                {
                    "ts_iso": _iso(ts),
                    "ts_unix_ms": _unix_ms(ts),
                    "pod_id": pod_id,
                    "rms_x_g": rms_x,
                    "rms_y_g": rms_y,
                    "rms_z_g": rms_z,
                    "peak_x_g": peak_x,
                    "peak_y_g": peak_y,
                    "peak_z_g": peak_z,
                    "band_low_g2": band_low,
                    "band_mid_g2": band_mid,
                    "band_high_g2": band_high,
                }
            )

    # Routine periodic raw burst capture, alternating pod, every few days.
    if day_index % ROUTINE_BURST_EVERY_N_DAYS == 0:
        pod_id = 1 if (day_index // ROUTINE_BURST_EVERY_N_DAYS) % 2 == 0 else 2
        ts = day_start + timedelta(hours=ROUTINE_BURST_HOUR)
        write_burst(rng, vib_dir, pod_id, ts, freq_hz=30.0, amplitude_g=0.04)

    # Injected knocking episode: sharp beater-pod (pod 1) vibration spike
    # with a strong low-frequency (5-50Hz band) raw-burst component.
    if day_index == KNOCK_DAY_INDEX:
        knock_ts = day_start + timedelta(seconds=KNOCK_OFFSET_S)
        rows.append(
            {
                "ts_iso": _iso(knock_ts),
                "ts_unix_ms": _unix_ms(knock_ts),
                "pod_id": 1,
                "rms_x_g": 0.34,
                "rms_y_g": 0.21,
                "rms_z_g": 1.18,
                "peak_x_g": 1.05,
                "peak_y_g": 0.68,
                "peak_z_g": 1.9,
                "band_low_g2": 0.62,
                "band_mid_g2": 0.09,
                "band_high_g2": 0.03,
            }
        )
        write_burst(rng, vib_dir, 1, knock_ts, freq_hz=9.0, amplitude_g=0.38)

    df = pd.DataFrame(rows, columns=VIB_SUMMARY_HEADER)
    return df.sort_values("ts_unix_ms").reset_index(drop=True)


# --------------------------------------------------------------------------
# events
# --------------------------------------------------------------------------


def build_events_day(day_index: int, day_start: datetime) -> list[dict]:
    events = []
    if day_index == 0:
        events.append(
            {
                "ts_iso": _iso(day_start),
                "ts_unix_ms": _unix_ms(day_start),
                "type": "system",
                "detail": {"msg": "boot", "firmware_version": FIRMWARE_VERSION},
            }
        )
        events.append(
            {
                "ts_iso": _iso(day_start + timedelta(seconds=3)),
                "ts_unix_ms": _unix_ms(day_start + timedelta(seconds=3)),
                "type": "system",
                "detail": {"msg": "config loaded", "deployment_id": DEPLOYMENT_ID},
            }
        )
    else:
        events.append(
            {
                "ts_iso": _iso(day_start),
                "ts_unix_ms": _unix_ms(day_start),
                "type": "system",
                "detail": {"msg": f"channels_{day_start:%Y%m%d}.csv rotation"},
            }
        )

    if day_index == KNOCK_DAY_INDEX:
        knock_ts = day_start + timedelta(seconds=KNOCK_OFFSET_S)
        button_ts = knock_ts + timedelta(seconds=KNOCK_BUTTON_DELAY_S)
        events.append(
            {
                "ts_iso": _iso(knock_ts),
                "ts_unix_ms": _unix_ms(knock_ts),
                "type": "trigger",
                "detail": {"reason": "vibration_spike", "pod_id": 1, "channel": "vib_pod_1"},
            }
        )
        events.append(
            {
                "ts_iso": _iso(button_ts),
                "ts_unix_ms": _unix_ms(button_ts),
                "type": "button",
                "detail": {
                    "button": "event_journal",
                    "note": "staff reported a knocking/rattling noise from the freezing cylinder",
                },
            }
        )

    return events


# --------------------------------------------------------------------------
# manifest / config
# --------------------------------------------------------------------------


def write_manifest(out_dir: Path) -> None:
    manifest = {
        "schema_version": 1,
        "deployment_id": DEPLOYMENT_ID,
        "machine_model": MACHINE_MODEL,
        "machine_serial": MACHINE_SERIAL,
        "technician": TECHNICIAN,
        "firmware_version": FIRMWARE_VERSION,
        "start_ts_iso": _iso(START_DATE),
        "channel_map": {
            "current_beater_a": {"location": "beater motor leg", "calibration": "30A/1V CT"},
            "current_compressor_a": {
                "location": "compressor contactor leg",
                "calibration": "30A/1V CT",
            },
            "temp_cylinder_c": {
                "location": "freezing cylinder jacket",
                "calibration": "DS18B20 28-0000demo0001",
            },
            "temp_cond_in_c": {
                "location": "condenser air intake",
                "calibration": "DS18B20 28-0000demo0002",
            },
            "temp_cond_out_c": {
                "location": "condenser air discharge",
                "calibration": "DS18B20 28-0000demo0003",
            },
            "temp_ambient_c": {
                "location": "compartment ambient",
                "calibration": "DS18B20 28-0000demo0004",
            },
            "temp_hopper_c": {
                "location": "hopper",
                "calibration": "DS18B20 28-0000demo0005",
            },
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
                "periodic_interval_s": VIB_INTERVAL_S,
            },
        },
    }
    with open(out_dir / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")


def write_config(out_dir: Path) -> None:
    config = {
        "deployment_id": DEPLOYMENT_ID,
        "machine_serial": MACHINE_SERIAL,
        "technician": TECHNICIAN,
    }
    with open(out_dir / "config.json", "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)
        fh.write("\n")


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------


def generate(out_dir: Path, seed: int = SEED) -> Path:
    rng = np.random.default_rng(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    vib_dir = out_dir / "vibration"
    vib_dir.mkdir(parents=True, exist_ok=True)

    write_manifest(out_dir)
    write_config(out_dir)

    carry: dict = {}
    for day_index in range(N_DAYS):
        day_start = START_DATE + timedelta(days=day_index)

        channels_df, beater_on, compressor_cmd = build_channels_day(rng, day_index, day_start, carry)
        channels_path = out_dir / f"channels_{day_start:%Y%m%d}.csv"
        channels_df.to_csv(channels_path, index=False, float_format="%.3f")
        del channels_df

        vib_df = build_vib_summary_day(rng, day_index, day_start, beater_on, compressor_cmd, vib_dir)
        vib_path = vib_dir / f"vib_summary_{day_start:%Y%m%d}.csv"
        vib_df.to_csv(vib_path, index=False, float_format="%.5f")
        del vib_df

        events = build_events_day(day_index, day_start)
        events_path = out_dir / f"events_{day_start:%Y%m%d}.jsonl"
        with open(events_path, "w", encoding="utf-8") as fh:
            for event in events:
                fh.write(json.dumps(event) + "\n")

        print(f"day {day_index + 1}/{N_DAYS} ({day_start:%Y-%m-%d}) written")

    return out_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output deployment directory (default: a fresh mkdtemp directory)",
    )
    parser.add_argument("--seed", type=int, default=SEED, help=f"RNG seed (default: {SEED})")
    args = parser.parse_args(argv)

    out_dir = args.out_dir
    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="frosty-demo-deployment-"))

    out_dir = generate(out_dir, seed=args.seed)
    print(f"Wrote demo deployment to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
