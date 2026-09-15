"""Synthetic failure-mode data generators for developing and testing
signature detectors (`frosty_analysis.signatures`) without field data.

Every ``make_*`` function returns a `SyntheticSegment`: a small, duck-typed
stand-in for `frosty_analysis.loader.Deployment` that exposes `.channels`
(the canonical per-second channel table) and `.vib_summary` (the periodic
vibration-burst summary table), in the exact column shapes
`frosty_analysis.loader.load_deployment` produces — tz-aware UTC
`DatetimeIndex`, same column names/order. `detect_*` functions in
`frosty_analysis.signatures` accept a `SyntheticSegment` directly, a bare
`Deployment`, or a bare channels `DataFrame`.

These are illustrative, not calibrated. Thresholds and magnitudes below are
chosen to make each failure mode visually and numerically obvious for a
demo/gallery and for exercising detector logic — not fit to bench or field
data. See `docs/firmware/data-format-spec.md` for the authoritative column
definitions and units.

All generators are seeded (accept a `numpy.random.Generator` or an int
seed) for reproducibility.

Resolution note — `make_motor_degradation` is the one exception to "one row
per second." Motor wear plays out over weeks, and a second-by-second
simulation over that span is unnecessary weight for an illustrative
example, so it samples at a coarser interval (5 minutes by default) and
says so in its docstring and in the segment's `.notes`. Every other
generator is 1Hz, matching `channels_YYYYMMDD.csv` on the card.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from frosty_analysis.loader import CHANNELS_COLUMNS, VIB_SUMMARY_COLUMNS, VibrationBurst

# --- shared "healthy" physical baselines --------------------------------
# Per the task brief: beater ~2.5-3.5A during service, compressor ~7A
# running with 4-8 min cycles, condenser dT ~8-12C when running, discharge
# ~80-90C. These are illustrative starting points, not calibrated values.

AMBIENT_C_DEFAULT = 25.0

BEATER_LOADED_RANGE = (2.5, 3.5)  # amps, normal service load
BEATER_ELEVATED_RANGE = (4.0, 5.2)  # amps, straining against too-firm product
BEATER_UNLOADED_RANGE = (0.8, 1.3)  # amps, spinning with (near) no mechanical load

COMPRESSOR_RUN_RANGE = (6.7, 7.3)  # amps while running

COND_DELTA_HEALTHY = (8.0, 12.0)  # degC, condenser air out - in, while running
DISCHARGE_HEALTHY = (80.0, 90.0)  # degC, compressor discharge line, while running

RUN_RANGE_HEALTHY_S = (4 * 60, 8 * 60)  # seconds, normal freeze-down run length
HOLD_RANGE_HEALTHY_S = (60, 180)  # seconds, normal idle/hold between runs

RUN_RANGE_SHORT_CYCLE_S = (20, 55)  # seconds, well under the 60s "short cycle" line
HOLD_RANGE_SHORT_CYCLE_S = (15, 45)  # seconds

_COLUMNS = [c for c in CHANNELS_COLUMNS if c != "ts_iso"]
_VIB_COLUMNS = [c for c in VIB_SUMMARY_COLUMNS if c != "ts_iso"]

POD_BEATER = 1
POD_COMPRESSOR = 2


@dataclass
class SyntheticSegment:
    """A synthetic stand-in for a `Deployment`, scoped to one illustrative
    scenario (healthy baseline or one failure mode).

    Duck-types the two pieces `frosty_analysis.signatures` detectors read:
    `.channels` and `.vib_summary`. `bursts` holds any raw
    `VibrationBurst` captures generated for the scenario (only `make_knocking`
    produces one, illustrating the 8-15Hz content a spectrogram would show);
    it's empty for scenarios that don't need one.
    """

    label: str
    channels: pd.DataFrame
    vib_summary: pd.DataFrame
    bursts: list[VibrationBurst] = field(default_factory=list)
    notes: str = ""


def _rng(rng: np.random.Generator | int | None) -> np.random.Generator:
    if isinstance(rng, np.random.Generator):
        return rng
    return np.random.default_rng(rng)


def _utc_index(
    n_rows: int, *, freq_s: float = 1.0, start: pd.Timestamp | None = None
) -> pd.DatetimeIndex:
    if start is None:
        start = pd.Timestamp("2026-06-01T00:00:00Z")
    return pd.date_range(
        start=start, periods=n_rows, freq=pd.Timedelta(seconds=freq_s), tz="UTC", name="ts"
    )


def _base_frame(index: pd.DatetimeIndex, ambient_c: float) -> pd.DataFrame:
    n = len(index)
    df = pd.DataFrame(index=index, columns=_COLUMNS, dtype="float64")
    df["ts_unix_ms"] = (index.asi8 // 1000).astype("int64")
    df["current_beater_a"] = 0.0
    df["current_compressor_a"] = 0.0
    df["temp_cylinder_c"] = ambient_c
    df["temp_cond_in_c"] = ambient_c
    df["temp_cond_out_c"] = ambient_c
    df["temp_ambient_c"] = ambient_c
    df["temp_hopper_c"] = np.nan  # optional probe, left unwired per spec
    df["temp_discharge_c"] = ambient_c
    df["beater_on"] = 0
    df["compressor_cmd"] = 0
    df["tcc_satisfied"] = 0
    df["hp_ok"] = 1
    return df


def _cycle_windows(
    n_rows: int,
    run_range: tuple[float, float],
    hold_range: tuple[float, float],
    rng: np.random.Generator,
) -> list[tuple[int, int, int]]:
    """Tile `[0, n_rows)` with alternating (run, hold) windows.

    Units are row-index counts, not necessarily seconds -- callers using a
    coarser sample interval (e.g. `make_motor_degradation`) pass
    already-scaled ranges. Returns a list of `(run_start, run_end, hold_end)`
    row-index tuples.
    """
    windows = []
    t = 0
    while t < n_rows:
        run_len = max(1, int(round(rng.uniform(*run_range))))
        hold_len = max(0, int(round(rng.uniform(*hold_range))))
        run_start = t
        run_end = min(t + run_len, n_rows)
        hold_end = min(run_end + hold_len, n_rows)
        windows.append((run_start, run_end, hold_end))
        t = hold_end
        if run_end >= n_rows:
            break
    return windows


def _col(df: pd.DataFrame, name: str) -> int:
    return df.columns.get_loc(name)


def _fill_cycle(
    df: pd.DataFrame,
    rng: np.random.Generator,
    run_start: int,
    run_end: int,
    hold_end: int,
    *,
    ambient_c: float,
    beater_current_range: tuple[float, float] | None,
    compressor_current_range: tuple[float, float] | None,
    cond_delta_range: tuple[float, float],
    discharge_range: tuple[float, float],
    tcc_pulse: bool = True,
    cylinder_floor_drop: tuple[float, float] = (20.0, 28.0),
) -> None:
    """Fill one run/hold cycle's worth of rows in place.

    `compressor_current_range=None` skips driving the compressor (used by
    `make_belt_slip`, where the compressor track is untouched and only the
    beater is anomalous). `beater_current_range=None` likewise skips the
    beater.
    """
    n = len(df)
    run_end = min(run_end, n)
    hold_end = min(hold_end, n)
    run_len = run_end - run_start
    if run_len <= 0:
        return

    idx = slice(run_start, run_end)

    if compressor_current_range is not None:
        df.iloc[run_start:run_end, _col(df, "compressor_cmd")] = 1
        df.iloc[run_start:run_end, _col(df, "current_compressor_a")] = rng.normal(
            np.mean(compressor_current_range), 0.2, run_len
        )
        cond_delta = rng.uniform(*cond_delta_range)
        df.iloc[run_start:run_end, _col(df, "temp_cond_in_c")] = ambient_c + rng.normal(
            0, 0.3, run_len
        )
        df.iloc[run_start:run_end, _col(df, "temp_cond_out_c")] = (
            ambient_c + cond_delta + rng.normal(0, 0.4, run_len)
        )
        discharge = rng.uniform(*discharge_range)
        df.iloc[run_start:run_end, _col(df, "temp_discharge_c")] = discharge + rng.normal(
            0, 1.5, run_len
        )

    if beater_current_range is not None:
        df.iloc[run_start:run_end, _col(df, "beater_on")] = 1
        df.iloc[run_start:run_end, _col(df, "current_beater_a")] = rng.uniform(
            *beater_current_range
        ) + rng.normal(0, 0.15, run_len)

    # Cylinder jacket temp asymptotically approaches a cold floor while
    # running (exponential, not linear -- a long run plateaus rather than
    # over-shooting), and relaxes back toward ambient during the hold.
    cyl_floor = ambient_c - rng.uniform(*cylinder_floor_drop)
    tau = max(run_len / 4.0, 30.0)
    t = np.arange(run_len)
    df.iloc[run_start:run_end, _col(df, "temp_cylinder_c")] = (
        cyl_floor + (ambient_c - cyl_floor) * np.exp(-t / tau) + rng.normal(0, 0.3, run_len)
    )

    if tcc_pulse and run_len > 10 and compressor_current_range is not None:
        pulse_len = min(max(1, int(rng.uniform(5, 15))), run_len)
        pulse_start = run_end - pulse_len
        df.iloc[pulse_start:run_end, _col(df, "tcc_satisfied")] = 1

    hold_len = hold_end - run_end
    if hold_len > 0:
        last_cond_out = df.iloc[run_end - 1, _col(df, "temp_cond_out_c")]
        last_discharge = df.iloc[run_end - 1, _col(df, "temp_discharge_c")]
        last_cyl = df.iloc[run_end - 1, _col(df, "temp_cylinder_c")]
        decay = np.linspace(1, 0, hold_len)
        df.iloc[run_end:hold_end, _col(df, "temp_cond_out_c")] = (
            ambient_c + (last_cond_out - ambient_c) * decay
        )
        df.iloc[run_end:hold_end, _col(df, "temp_discharge_c")] = (
            ambient_c + (last_discharge - ambient_c) * decay
        )
        df.iloc[run_end:hold_end, _col(df, "temp_cylinder_c")] = (
            ambient_c + (last_cyl - ambient_c) * decay * 0.5
        )
        df.iloc[run_end:hold_end, _col(df, "temp_cond_in_c")] = ambient_c + rng.normal(
            0, 0.3, hold_len
        )


# --- vibration summary -----------------------------------------------------


def _vib_baseline_row(pod_id: int, running: bool, rng: np.random.Generator) -> dict:
    rms = rng.uniform(0.04, 0.09) if running else rng.uniform(0.005, 0.02)
    band_low = rms**2 * rng.uniform(0.70, 0.90)
    band_mid = rms**2 * rng.uniform(0.05, 0.20)
    band_high = rms**2 * rng.uniform(0.01, 0.05)
    peak = rms * rng.uniform(2.5, 4.0)
    return {
        "pod_id": pod_id,
        "rms_x_g": rms * rng.uniform(0.85, 1.15),
        "rms_y_g": rms * rng.uniform(0.85, 1.15),
        "rms_z_g": rms * rng.uniform(0.85, 1.15),
        "peak_x_g": peak * rng.uniform(0.85, 1.15),
        "peak_y_g": peak * rng.uniform(0.85, 1.15),
        "peak_z_g": peak * rng.uniform(0.85, 1.15),
        "band_low_g2": band_low,
        "band_mid_g2": band_mid,
        "band_high_g2": band_high,
    }


def _make_vib_summary(
    n_rows: int,
    start: pd.Timestamp,
    windows: list[tuple[int, int, int]],
    rng: np.random.Generator,
    *,
    interval_s: int = 60,
    pod1_override=None,
) -> pd.DataFrame:
    """Periodic vibration-burst summary rows for both pods across the segment.

    `pod1_override(t_row, running, base_row, rng) -> dict` lets callers
    inject anomalies on the beater-drive pod (knocking, belt slip) while
    the compressor pod (`pod_id=2`) stays at baseline.
    """
    records = []
    timestamps = []
    for t in range(0, n_rows, interval_s):
        running = any(run_s <= t < run_e for run_s, run_e, _ in windows)
        ts = start + pd.Timedelta(seconds=t)

        base1 = _vib_baseline_row(POD_BEATER, running, rng)
        if pod1_override is not None:
            base1 = pod1_override(t, running, base1, rng)
        records.append(base1)
        timestamps.append(ts)

        base2 = _vib_baseline_row(POD_COMPRESSOR, running, rng)
        records.append(base2)
        timestamps.append(ts)

    if not records:
        df = pd.DataFrame(columns=_VIB_COLUMNS)
        df.index = pd.DatetimeIndex([], tz="UTC", name="ts")
        return df

    df = pd.DataFrame.from_records(records, columns=_VIB_COLUMNS)
    df.index = pd.DatetimeIndex(timestamps, name="ts")
    df = df.sort_index()
    return df


# --- generators --------------------------------------------------------


def make_healthy(
    hours: float = 6.0,
    rng: np.random.Generator | int | None = None,
    start: pd.Timestamp | None = None,
    ambient_c: float = AMBIENT_C_DEFAULT,
) -> SyntheticSegment:
    """Healthy baseline: normal 4-8 minute freeze-down cycles, condenser
    delta-T and discharge temp in range, TCC satisfies at the end of every
    run, vibration at quiet baseline levels.
    """
    rng = _rng(rng)
    if start is None:
        start = pd.Timestamp("2026-06-01T00:00:00Z")
    n_rows = int(hours * 3600)
    idx = _utc_index(n_rows, start=start)
    df = _base_frame(idx, ambient_c)

    windows = _cycle_windows(n_rows, RUN_RANGE_HEALTHY_S, HOLD_RANGE_HEALTHY_S, rng)
    for run_start, run_end, hold_end in windows:
        _fill_cycle(
            df,
            rng,
            run_start,
            run_end,
            hold_end,
            ambient_c=ambient_c,
            beater_current_range=BEATER_LOADED_RANGE,
            compressor_current_range=COMPRESSOR_RUN_RANGE,
            cond_delta_range=COND_DELTA_HEALTHY,
            discharge_range=DISCHARGE_HEALTHY,
        )

    vib = _make_vib_summary(n_rows, start, windows, rng)
    return SyntheticSegment(
        label="healthy",
        channels=df,
        vib_summary=vib,
        notes="Healthy baseline: 4-8 min run / 1-3 min hold cycles, TCC "
        "satisfies at the end of every run, condenser dT 8-12C, "
        "discharge 80-90C, vibration at quiet baseline.",
    )


def make_short_cycling(
    hours: float = 4.0,
    rng: np.random.Generator | int | None = None,
    start: pd.Timestamp | None = None,
    ambient_c: float = AMBIENT_C_DEFAULT,
) -> SyntheticSegment:
    """Compressor short-cycling: run lengths shrink to well under 60s, back
    to back, all else (condenser dT, discharge, TCC) left in a normal range
    so this segment isolates the run-length signal from other failure
    signatures (see `test_signatures.py`'s short-cycling-vs-condenser
    cross-check).
    """
    rng = _rng(rng)
    if start is None:
        start = pd.Timestamp("2026-06-02T00:00:00Z")
    n_rows = int(hours * 3600)
    idx = _utc_index(n_rows, start=start)
    df = _base_frame(idx, ambient_c)

    windows = _cycle_windows(
        n_rows, RUN_RANGE_SHORT_CYCLE_S, HOLD_RANGE_SHORT_CYCLE_S, rng
    )
    for run_start, run_end, hold_end in windows:
        _fill_cycle(
            df,
            rng,
            run_start,
            run_end,
            hold_end,
            ambient_c=ambient_c,
            beater_current_range=BEATER_LOADED_RANGE,
            compressor_current_range=COMPRESSOR_RUN_RANGE,
            cond_delta_range=COND_DELTA_HEALTHY,
            discharge_range=DISCHARGE_HEALTHY,
            tcc_pulse=False,  # runs are too short to ever reach cutout
        )

    vib = _make_vib_summary(n_rows, start, windows, rng)
    return SyntheticSegment(
        label="short_cycling",
        channels=df,
        vib_summary=vib,
        notes="Compressor run lengths shrink to 20-55s (vs. 4-8min "
        "healthy), back to back -- classic low-refrigerant-charge "
        "short-cycling. Condenser dT/discharge left healthy on purpose.",
    )


def make_tcc_never_satisfied(
    hours: float = 5.0,
    rng: np.random.Generator | int | None = None,
    start: pd.Timestamp | None = None,
    ambient_c: float = AMBIENT_C_DEFAULT,
) -> SyntheticSegment:
    """"Won't freeze": compressor and beater commanded on continuously for
    the whole segment, TCC never trips, beater current elevated (straining
    against product that never sets up).
    """
    rng = _rng(rng)
    if start is None:
        start = pd.Timestamp("2026-06-03T00:00:00Z")
    n_rows = int(hours * 3600)
    idx = _utc_index(n_rows, start=start)
    df = _base_frame(idx, ambient_c)

    windows = [(0, n_rows, n_rows)]
    _fill_cycle(
        df,
        rng,
        0,
        n_rows,
        n_rows,
        ambient_c=ambient_c,
        beater_current_range=BEATER_ELEVATED_RANGE,
        compressor_current_range=COMPRESSOR_RUN_RANGE,
        cond_delta_range=COND_DELTA_HEALTHY,
        discharge_range=DISCHARGE_HEALTHY,
        tcc_pulse=False,
    )

    vib = _make_vib_summary(n_rows, start, windows, rng)
    return SyntheticSegment(
        label="tcc_never_satisfied",
        channels=df,
        vib_summary=vib,
        notes="Compressor+beater commanded on for the entire segment, "
        "tcc_satisfied never asserts, beater current elevated "
        "(4.0-5.2A vs 2.5-3.5A healthy).",
    )


def make_condenser_airflow(
    hours: float = 10.0,
    rng: np.random.Generator | int | None = None,
    start: pd.Timestamp | None = None,
    ambient_c: float = AMBIENT_C_DEFAULT,
) -> SyntheticSegment:
    """Clogged condenser / blocked airflow: normal run/hold cycling and a
    normal TCC pattern (isolates this signature from short-cycling/TCC
    signatures), but condenser delta-T collapses from healthy toward ~2-4C
    and discharge/ambient climb over the course of the segment, as a
    clogged coil or blocked vent recirculates heat.
    """
    rng = _rng(rng)
    if start is None:
        start = pd.Timestamp("2026-06-04T00:00:00Z")
    n_rows = int(hours * 3600)
    idx = _utc_index(n_rows, start=start)
    df = _base_frame(idx, ambient_c)

    windows = _cycle_windows(n_rows, RUN_RANGE_HEALTHY_S, HOLD_RANGE_HEALTHY_S, rng)
    for run_start, run_end, hold_end in windows:
        _fill_cycle(
            df,
            rng,
            run_start,
            run_end,
            hold_end,
            ambient_c=ambient_c,
            beater_current_range=BEATER_LOADED_RANGE,
            compressor_current_range=COMPRESSOR_RUN_RANGE,
            cond_delta_range=COND_DELTA_HEALTHY,
            discharge_range=DISCHARGE_HEALTHY,
        )

    # Layer a worsening-over-time airflow blockage on top of the otherwise
    # healthy cycling: delta-T collapses toward the end, discharge and
    # ambient/cond-in climb.
    frac = np.linspace(0.0, 1.0, n_rows)
    compressor_on = df["compressor_cmd"].to_numpy() == 1
    target_delta_late = rng.uniform(1.5, 3.5)
    baseline_delta = (df["temp_cond_out_c"] - df["temp_cond_in_c"]).to_numpy()
    new_delta = baseline_delta * (1 - frac) + target_delta_late * frac

    # Ambient/cond-in rises first (heat recirculating around the blocked
    # coil), *then* cond-out is derived from the already-risen cond-in
    # plus the intended (collapsing) delta-T -- so the final measured
    # delta-T lands on `new_delta`, not `new_delta` minus the ambient rise.
    ambient_add = frac * rng.uniform(6.0, 10.0)
    df["temp_ambient_c"] = df["temp_ambient_c"].to_numpy() + ambient_add
    df["temp_cond_in_c"] = df["temp_cond_in_c"].to_numpy() + ambient_add

    cond_out = df["temp_cond_out_c"].to_numpy().copy()
    cond_out[compressor_on] = (
        df["temp_cond_in_c"].to_numpy()[compressor_on] + new_delta[compressor_on]
    )
    df["temp_cond_out_c"] = cond_out

    discharge_add = frac * rng.uniform(20.0, 30.0)
    discharge = df["temp_discharge_c"].to_numpy().copy()
    discharge[compressor_on] += discharge_add[compressor_on]
    df["temp_discharge_c"] = discharge

    vib = _make_vib_summary(n_rows, start, windows, rng)
    return SyntheticSegment(
        label="condenser_airflow",
        channels=df,
        vib_summary=vib,
        notes="Run/hold cycling and TCC pattern left healthy; condenser "
        "delta-T collapses from ~8-12C toward ~1.5-3.5C and discharge "
        "climbs ~20-30C over the segment as blockage worsens.",
    )


def make_knocking(
    hours: float = 5.0,
    rng: np.random.Generator | int | None = None,
    start: pd.Timestamp | None = None,
    ambient_c: float = AMBIENT_C_DEFAULT,
) -> SyntheticSegment:
    """Knocking during freeze-down: otherwise-healthy cycling, but the
    beater-drive pod (`pod_id=1`) shows clustered RMS spikes (several x
    baseline) during a handful of runs, concentrated in the freeze-down
    portion. Also produces one raw `VibrationBurst` with strong 8-15Hz
    content, illustrating what a spectrogram of a knock event looks like.
    """
    rng = _rng(rng)
    if start is None:
        start = pd.Timestamp("2026-06-05T00:00:00Z")
    n_rows = int(hours * 3600)
    idx = _utc_index(n_rows, start=start)
    df = _base_frame(idx, ambient_c)

    windows = _cycle_windows(n_rows, RUN_RANGE_HEALTHY_S, HOLD_RANGE_HEALTHY_S, rng)
    for run_start, run_end, hold_end in windows:
        _fill_cycle(
            df,
            rng,
            run_start,
            run_end,
            hold_end,
            ambient_c=ambient_c,
            beater_current_range=BEATER_LOADED_RANGE,
            compressor_current_range=COMPRESSOR_RUN_RANGE,
            cond_delta_range=COND_DELTA_HEALTHY,
            discharge_range=DISCHARGE_HEALTHY,
        )

    # Pick roughly every 3rd run window to have a knock cluster in its
    # first third (ice/air knocking is most common early in freeze-down).
    knock_windows = set()
    knock_row_ranges = []
    for i, (run_start, run_end, _hold_end) in enumerate(windows):
        if i % 3 == 0 and run_end > run_start:
            knock_start = run_start
            knock_end = run_start + max(1, (run_end - run_start) // 3)
            knock_windows.add(i)
            knock_row_ranges.append((knock_start, knock_end))

    def pod1_override(t_row, running, base_row, rng_):
        for knock_start, knock_end in knock_row_ranges:
            if knock_start <= t_row < knock_end:
                mult = rng_.uniform(5.0, 8.0)
                base_row["rms_x_g"] *= mult
                base_row["rms_y_g"] *= mult
                base_row["rms_z_g"] *= mult
                base_row["peak_x_g"] *= mult * 1.3
                base_row["peak_y_g"] *= mult * 1.3
                base_row["peak_z_g"] *= mult * 1.3
                base_row["band_mid_g2"] *= mult**2 * 1.5
                base_row["band_high_g2"] *= mult**2
                break
        return base_row

    vib = _make_vib_summary(n_rows, start, windows, rng, pod1_override=pod1_override)

    # One illustrative raw burst: 1600Hz, ~2s, dominant energy at 8-15Hz
    # plus baseline broadband noise, taken from the middle of the first
    # knock cluster.
    bursts: list[VibrationBurst] = []
    if knock_row_ranges:
        burst_start_row = knock_row_ranges[0][0]
        sample_rate_hz = 1600
        duration_s = 2.0
        n_samples = int(sample_rate_hz * duration_s)
        t = np.arange(n_samples) / sample_rate_hz
        knock_freqs = rng.uniform(8.0, 15.0, size=3)
        data = np.zeros((n_samples, 3))
        for axis in range(3):
            signal_component = 0.6 * np.sin(2 * np.pi * knock_freqs[axis] * t)
            noise = rng.normal(0, 0.08, n_samples)
            data[:, axis] = signal_component + noise
        burst_start_ts = start + pd.Timedelta(seconds=burst_start_row)
        bursts.append(
            VibrationBurst(
                pod_id=POD_BEATER,
                sample_rate_hz=sample_rate_hz,
                start_ts=burst_start_ts,
                scale_g_per_lsb=1.0 / 4096,
                data=data,
            )
        )

    return SyntheticSegment(
        label="knocking",
        channels=df,
        vib_summary=vib,
        bursts=bursts,
        notes="Otherwise-healthy cycling; beater-pod RMS spikes 5-8x "
        "baseline in clusters near the start of ~1/3 of runs. One raw "
        "burst included with dominant 8-15Hz content.",
    )


def make_belt_slip(
    hours: float = 5.0,
    rng: np.random.Generator | int | None = None,
    start: pd.Timestamp | None = None,
    ambient_c: float = AMBIENT_C_DEFAULT,
) -> SyntheticSegment:
    """Slipping/broken drive belt: beater is commanded on (`beater_on=1`)
    through every run, same as healthy, but current sags to the unloaded
    range because the motor is no longer driving a mechanical load.
    Beater-pod vibration energy drops to match (a spinning-but-unloaded
    motor is quieter, not louder). Compressor track is left healthy so
    this isolates from the other signatures.
    """
    rng = _rng(rng)
    if start is None:
        start = pd.Timestamp("2026-06-06T00:00:00Z")
    n_rows = int(hours * 3600)
    idx = _utc_index(n_rows, start=start)
    df = _base_frame(idx, ambient_c)

    windows = _cycle_windows(n_rows, RUN_RANGE_HEALTHY_S, HOLD_RANGE_HEALTHY_S, rng)
    for run_start, run_end, hold_end in windows:
        _fill_cycle(
            df,
            rng,
            run_start,
            run_end,
            hold_end,
            ambient_c=ambient_c,
            beater_current_range=BEATER_UNLOADED_RANGE,
            compressor_current_range=COMPRESSOR_RUN_RANGE,
            cond_delta_range=COND_DELTA_HEALTHY,
            discharge_range=DISCHARGE_HEALTHY,
        )

    def pod1_override(t_row, running, base_row, rng_):
        if running:
            # Less mechanical load coupled into the frame -> lower RMS,
            # not higher.
            factor = rng_.uniform(0.25, 0.45)
            for key in ("rms_x_g", "rms_y_g", "rms_z_g", "peak_x_g", "peak_y_g", "peak_z_g"):
                base_row[key] *= factor
            for key in ("band_low_g2", "band_mid_g2", "band_high_g2"):
                base_row[key] *= factor**2
        return base_row

    vib = _make_vib_summary(n_rows, start, windows, rng, pod1_override=pod1_override)
    return SyntheticSegment(
        label="belt_slip",
        channels=df,
        vib_summary=vib,
        notes="beater_on=1 throughout every run (commanded normally), but "
        "current_beater_a sags to 0.8-1.3A (unloaded) instead of "
        "2.5-3.5A, and beater-pod vibration RMS drops to 25-45% of "
        "baseline.",
    )


def make_motor_degradation(
    days: int = 21,
    rng: np.random.Generator | int | None = None,
    start: pd.Timestamp | None = None,
    ambient_c: float = AMBIENT_C_DEFAULT,
    resolution_s: int = 300,
) -> SyntheticSegment:
    """Gradual beater-motor degradation over weeks.

    RESOLUTION NOTE: unlike every other generator in this module, this one
    does *not* produce one row per second. Motor wear plays out over
    weeks; a second-by-second simulation of `days` worth of data is a lot
    of memory and runtime for an illustrative example, so this samples at
    `resolution_s` (default 300s = 5 min) instead. The returned
    `.channels` DataFrame still has the canonical columns and a tz-aware
    UTC `DatetimeIndex` -- just spaced 5 minutes apart rather than 1
    second. `detect_motor_degradation` works on daily medians, so this
    resolution doesn't lose the signal it needs.

    Simulated failure: `current_beater_a` under load drifts upward,
    day over day, as bearings/windings wear -- from the healthy baseline
    up toward the elevated range over the course of the segment.
    """
    rng = _rng(rng)
    if start is None:
        start = pd.Timestamp("2026-06-01T00:00:00Z")
    n_rows = int(days * 86400 / resolution_s)
    idx = _utc_index(n_rows, freq_s=resolution_s, start=start)
    df = _base_frame(idx, ambient_c)

    # Run/hold ranges rescaled into "rows of resolution_s seconds" so the
    # duty cycle still looks like intermittent service use rather than
    # always-on.
    run_range_rows = (
        RUN_RANGE_HEALTHY_S[0] / resolution_s,
        RUN_RANGE_HEALTHY_S[1] / resolution_s * 3,  # a bit longer at coarse res
    )
    hold_range_rows = (
        HOLD_RANGE_HEALTHY_S[0] / resolution_s,
        HOLD_RANGE_HEALTHY_S[1] / resolution_s * 3,
    )
    windows = _cycle_windows(n_rows, run_range_rows, hold_range_rows, rng)
    for run_start, run_end, hold_end in windows:
        _fill_cycle(
            df,
            rng,
            run_start,
            run_end,
            hold_end,
            ambient_c=ambient_c,
            beater_current_range=BEATER_LOADED_RANGE,
            compressor_current_range=COMPRESSOR_RUN_RANGE,
            cond_delta_range=COND_DELTA_HEALTHY,
            discharge_range=DISCHARGE_HEALTHY,
        )

    # Day-indexed upward drift applied to loaded beater current only.
    seconds_per_row = resolution_s
    day_index = (np.arange(n_rows) * seconds_per_row) // 86400
    end_drift = rng.uniform(1.8, 2.4)  # amps added by the final day
    slope_per_day = end_drift / max(days - 1, 1)
    drift = day_index * slope_per_day

    beater_on = df["beater_on"].to_numpy() == 1
    current = df["current_beater_a"].to_numpy().copy()
    current[beater_on] += drift[beater_on]
    df["current_beater_a"] = current

    vib = _make_vib_summary(n_rows, start, windows, rng, interval_s=resolution_s)
    return SyntheticSegment(
        label="motor_degradation",
        channels=df,
        vib_summary=vib,
        notes=(
            f"Sampled at {resolution_s}s resolution (not 1Hz -- see "
            f"docstring) across {days} days. current_beater_a under load "
            f"drifts upward ~{slope_per_day:.3f}A/day, from the healthy "
            f"2.5-3.5A baseline toward +{end_drift:.1f}A by the end of the "
            "segment."
        ),
    )
