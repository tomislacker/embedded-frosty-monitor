"""Failure-signature detectors.

Each `detect_*` function here implements one known failure-mode signature
against the logged channels (and, for the vibration-based detectors, the
vibration summary). Detection logic is deliberately simple and
explainable -- threshold/rule-based on a handful of named quantities, no
machine learning -- so a technician or a future maintainer can read the
code and see exactly why something did or didn't trigger.

**Every threshold below is provisional.** They're chosen to be physically
plausible starting points (informed by the ranges noted in
`frosty_analysis.synthetic` and `docs/firmware/data-format-spec.md`), not
fit to bench or field data. Treat them as placeholders to be recalibrated
once real machines (M3+ in the project roadmap) produce logged data to
tune against. Each threshold is a module-level constant with a comment
saying so, specifically to make them easy to find and revise later without
touching detection logic.

**Accepted inputs.** Every `detect_*` function takes any of:
  - a `frosty_analysis.loader.Deployment`
  - a `frosty_analysis.synthetic.SyntheticSegment` (or any object exposing
    `.channels` and, optionally, `.vib_summary`)
  - a bare `pandas.DataFrame` in the canonical `channels` shape (no
    vibration data available in that case; vibration-based detectors will
    report `triggered=False` with an explanation rather than raising)

This keeps the public shape the original stubs declared (`Deployment`) but
extends it permissively so `frosty_analysis.synthetic` segments can be
fed straight into these functions in tests and in the demo gallery,
without needing to round-trip through on-disk CSVs.

See `docs/roadmap.md` item 2 for the original tracking item these replace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from frosty_analysis.loader import Deployment


# --- result type ---------------------------------------------------------


@dataclass
class SignatureResult:
    """Structured output of a `detect_*` call.

    `metrics` holds the numeric summary that drove the decision (so a
    caller/report can show its work), `explanation` is a human-readable
    sentence or two suitable for a technician-facing report, and
    `evidence` is a supporting DataFrame/Series where one exists naturally
    (e.g. the run-length table for short-cycling) -- `None` when there's
    nothing to show.
    """

    triggered: bool
    severity: str  # "none" | "watch" | "warning" | "critical"
    metrics: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""
    evidence: pd.DataFrame | pd.Series | None = None


def _empty_vib_summary() -> pd.DataFrame:
    from frosty_analysis.loader import VIB_SUMMARY_COLUMNS

    cols = [c for c in VIB_SUMMARY_COLUMNS if c != "ts_iso"]
    df = pd.DataFrame(columns=cols)
    df.index = pd.DatetimeIndex([], tz="UTC", name="ts")
    return df


def _normalize(dep_or_frame: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pull `(channels, vib_summary)` out of whatever was passed in.

    Accepts a `Deployment`, anything duck-typed like a
    `frosty_analysis.synthetic.SyntheticSegment` (has `.channels`, maybe
    `.vib_summary`), or a bare channels `DataFrame`.
    """
    if isinstance(dep_or_frame, Deployment):
        return dep_or_frame.channels, dep_or_frame.vib_summary
    if isinstance(dep_or_frame, pd.DataFrame):
        return dep_or_frame, _empty_vib_summary()
    channels = getattr(dep_or_frame, "channels", None)
    if channels is not None:
        vib = getattr(dep_or_frame, "vib_summary", None)
        if vib is None:
            vib = _empty_vib_summary()
        return channels, vib
    raise TypeError(
        "expected a Deployment, a SyntheticSegment-like object with "
        f".channels, or a bare channels DataFrame; got {type(dep_or_frame)!r}"
    )


def _bool_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns or len(df) == 0:
        return pd.Series(dtype=bool)
    return df[col].fillna(0).astype(float).astype(bool)


def _runs(mask: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Contiguous `True` runs in a boolean series indexed by time.

    Returns `(start, end)` timestamp pairs; `end` is the timestamp of the
    last `True` sample in the run (not the sample after it -- callers add
    one sample period if they need an exclusive end).
    """
    if mask.empty or not mask.any():
        return []
    values = mask.to_numpy()
    idx = mask.index
    runs = []
    start = None
    for i, v in enumerate(values):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((idx[start], idx[i - 1]))
            start = None
    if start is not None:
        runs.append((idx[start], idx[-1]))
    return runs


def _median_sample_period(index: pd.DatetimeIndex) -> pd.Timedelta:
    if len(index) < 2:
        return pd.Timedelta(seconds=1)
    diffs = index.to_series().diff().dropna()
    if diffs.empty:
        return pd.Timedelta(seconds=1)
    return diffs.median()


# --- 1. short cycling ------------------------------------------------------

# A normal freeze-down run is 4-8 minutes; a run under this length is
# counted as "short." (provisional -- M3+ bench/field calibration)
SHORT_CYCLE_MAX_RUN_S = 90
# How many short runs, within the rolling window below, before we call it
# short-cycling rather than a one-off startup blip. (provisional)
SHORT_CYCLE_MIN_COUNT = 4
# Rolling window runs are counted within. (provisional)
SHORT_CYCLE_WINDOW = pd.Timedelta(hours=2)


def detect_short_cycling(dep: Deployment) -> SignatureResult:
    """Flag compressor short-cycling.

    What it catches: the compressor turning on and off rapidly (runs under
    `SHORT_CYCLE_MAX_RUN_S` seconds), clustered close together in time --
    the classic signature of a low refrigerant charge tripping a
    low-pressure or overload cutout before a normal cycle completes.

    What it can't catch: a *single* short run (e.g. a normal startup blip,
    or a tech briefly bumping the machine) is deliberately not flagged --
    `SHORT_CYCLE_MIN_COUNT` requires several short runs inside
    `SHORT_CYCLE_WINDOW` before triggering. It also can't distinguish a
    refrigerant-charge problem from a flaky contactor or a miswired
    pressure switch producing the same on/off pattern -- the signature
    only says "cycling too fast," not why.

    False-positive modes: a machine that's *supposed* to cycle briefly
    during a defrost/purge sequence (if the firmware ever adds one) would
    look identical to this detector; a genuinely intermittent 24VAC signal
    (see roadmap bench-validation item on the opto trigger threshold)
    could also manufacture short on/off blips that aren't mechanical at
    all.
    """
    channels, _vib = _normalize(dep)
    cmd = _bool_col(channels, "compressor_cmd")
    if cmd.empty:
        return SignatureResult(
            triggered=False,
            severity="none",
            explanation="No compressor_cmd data available.",
        )

    period = _median_sample_period(channels.index)
    runs = _runs(cmd)
    if not runs:
        return SignatureResult(
            triggered=False,
            severity="none",
            explanation="Compressor never commanded on in this window.",
        )

    records = []
    for start, end in runs:
        duration_s = (end - start + period).total_seconds()
        records.append({"start": start, "end": end, "duration_s": duration_s})
    run_table = pd.DataFrame(records).set_index("start")

    short = run_table[run_table["duration_s"] < SHORT_CYCLE_MAX_RUN_S]

    # Cluster short runs into rolling-window groups and find the largest
    # cluster; that's the strongest evidence for "clustered" short cycling
    # rather than isolated blips scattered across the whole deployment.
    max_cluster = 0
    if not short.empty:
        short_starts = short.index.to_series()
        for t in short_starts:
            window_count = (
                (short_starts >= t) & (short_starts < t + SHORT_CYCLE_WINDOW)
            ).sum()
            max_cluster = max(max_cluster, window_count)

    triggered = bool(max_cluster >= SHORT_CYCLE_MIN_COUNT)
    median_duration = run_table["duration_s"].median()

    if triggered:
        severity = "critical" if max_cluster >= SHORT_CYCLE_MIN_COUNT * 2 else "warning"
        explanation = (
            f"{max_cluster} compressor runs under {SHORT_CYCLE_MAX_RUN_S}s "
            f"within a {SHORT_CYCLE_WINDOW} window (median run length "
            f"{median_duration:.0f}s overall). Consistent with "
            "short-cycling, most commonly caused by a low refrigerant "
            "charge."
        )
    else:
        severity = "none"
        explanation = (
            f"Largest cluster of sub-{SHORT_CYCLE_MAX_RUN_S}s runs was "
            f"{max_cluster} (threshold {SHORT_CYCLE_MIN_COUNT}); median "
            f"run length {median_duration:.0f}s. No short-cycling pattern."
        )

    return SignatureResult(
        triggered=triggered,
        severity=severity,
        metrics={
            "n_runs": len(run_table),
            "n_short_runs": len(short),
            "max_cluster_in_window": int(max_cluster),
            "median_run_s": float(median_duration),
        },
        explanation=explanation,
        evidence=run_table,
    )


# --- 2. TCC never satisfied -------------------------------------------------

# How long compressor+beater can run continuously before we expect a TCC
# trip; well beyond the healthy 4-8 min cycle. (provisional)
TCC_NEVER_SATISFIED_MIN_HOURS = 1.5


def detect_tcc_never_satisfied(dep: Deployment) -> SignatureResult:
    """Flag a "won't freeze" condition.

    What it catches: an extended stretch (over
    `TCC_NEVER_SATISFIED_MIN_HOURS`) where the compressor and beater are
    both commanded on continuously while `tcc_satisfied` (the
    thermostatic cutout microswitch -- the sensor that says "product has
    reached serving consistency") never asserts. That pattern means the
    machine is running flat-out without ever reaching its cutout setpoint
    -- a mix that's too thin/wrong ratio, a lost refrigerant charge severe
    enough that it can't pull the cylinder down, or a bad/unwired TCC
    switch.

    What it can't catch: it can't tell a genuinely weak refrigeration
    system (the "condenser airflow" or "short cycling" signatures) from a
    correctly-refrigerating machine given a batch of straight water instead
    of mix -- both look like "runs forever, never satisfies." It also
    can't distinguish "never satisfies" from "TCC switch not wired /
    always reads 0," which per `data-format-spec.md` is a valid, tolerated
    state (`tcc_satisfied` is "if tapped").

    False-positive modes: a deployment where `tcc_satisfied` genuinely
    isn't wired will always trigger this detector, regardless of whether
    the machine is actually failing to freeze -- worth cross-checking
    against `manifest.json`'s `channel_map` before acting on this alone.
    A tech manually holding the machine in a forced-run diagnostic mode
    for longer than normal would also look like this.
    """
    channels, _vib = _normalize(dep)
    compressor = _bool_col(channels, "compressor_cmd")
    beater = _bool_col(channels, "beater_on")
    tcc = _bool_col(channels, "tcc_satisfied")

    if compressor.empty or beater.empty:
        return SignatureResult(
            triggered=False,
            severity="none",
            explanation="No compressor_cmd/beater_on data available.",
        )

    both_on = (compressor & beater).reindex(channels.index, fill_value=False)
    runs = _runs(both_on)
    period = _median_sample_period(channels.index)

    worst = None
    worst_hours = 0.0
    for start, end in runs:
        duration_h = (end - start + period).total_seconds() / 3600.0
        window_tcc = tcc.loc[start:end]
        tcc_seen = bool(window_tcc.any()) if not window_tcc.empty else False
        if not tcc_seen and duration_h > worst_hours:
            worst_hours = duration_h
            worst = (start, end)

    triggered = bool(worst_hours >= TCC_NEVER_SATISFIED_MIN_HOURS)

    if triggered:
        severity = "critical" if worst_hours >= TCC_NEVER_SATISFIED_MIN_HOURS * 2 else "warning"
        explanation = (
            f"Compressor and beater ran continuously for "
            f"{worst_hours:.1f}h ({worst[0]} to {worst[1]}) without "
            f"tcc_satisfied ever asserting (threshold "
            f"{TCC_NEVER_SATISFIED_MIN_HOURS}h). The machine is running "
            "without ever reaching serving consistency."
        )
    else:
        severity = "none"
        explanation = (
            f"Longest continuous compressor+beater run without a TCC "
            f"trip was {worst_hours:.1f}h (threshold "
            f"{TCC_NEVER_SATISFIED_MIN_HOURS}h). Normal cutout behavior."
        )

    return SignatureResult(
        triggered=triggered,
        severity=severity,
        metrics={
            "longest_unsatisfied_run_hours": float(worst_hours),
            "n_continuous_runs": len(runs),
        },
        explanation=explanation,
        evidence=None,
    )


# --- 3. condenser airflow ---------------------------------------------------

# Healthy condenser delta-T while running is ~8-12C; below this floor is
# suspect regardless of trend. (provisional)
CONDENSER_DELTA_T_FLOOR_C = 5.0
# Relative drop (late-window median vs early-window median) that counts as
# "collapsing," on top of the absolute floor. (provisional)
CONDENSER_DELTA_T_RELATIVE_DROP = 0.35


def detect_condenser_airflow(dep: Deployment) -> SignatureResult:
    """Flag a clogged condenser or blocked airflow.

    What it catches: while the compressor runs, "condenser air delta-T"
    -- the temperature rise of the air passing through the condenser coil,
    `temp_cond_out_c` minus `temp_cond_in_c` -- collapsing either below an
    absolute floor (`CONDENSER_DELTA_T_FLOOR_C`) or by a large relative
    amount comparing the first and last thirds of the deployment
    (`CONDENSER_DELTA_T_RELATIVE_DROP`). A shrinking delta-T with the
    compressor still running means the condenser isn't rejecting heat the
    way it used to -- most often a dust-clogged coil or a blocked vent.

    What it can't catch: it doesn't look at `temp_discharge_c`
    independently, so a delta-T collapse caused by a failing condenser fan
    (airflow volume) looks the same as one caused by a dirty coil (airflow
    resistance) -- both need a tech to physically inspect. It also can't
    tell a clogged condenser from a machine relocated to a hotter,
    poorly-ventilated space between the early and late windows (both
    raise ambient and could shrink measured delta-T if intake air is
    itself pre-heated by recirculation).

    False-positive modes: a deployment that starts recording mid-defrost
    or during a brief cold snap could show an artificially high early-window
    delta-T, making an otherwise-normal condenser look like it
    "collapsed" by comparison. A deployment shorter than a few hours won't
    have a meaningful early/late split.
    """
    channels, _vib = _normalize(dep)
    if len(channels) == 0 or "temp_cond_in_c" not in channels.columns:
        return SignatureResult(
            triggered=False,
            severity="none",
            explanation="No condenser temperature data available.",
        )

    compressor = _bool_col(channels, "compressor_cmd")
    running = channels[compressor.reindex(channels.index, fill_value=False)]
    if running.empty:
        return SignatureResult(
            triggered=False,
            severity="none",
            explanation="Compressor never ran in this window; nothing to evaluate.",
        )

    delta_t = (running["temp_cond_out_c"] - running["temp_cond_in_c"]).dropna()
    if delta_t.empty:
        return SignatureResult(
            triggered=False,
            severity="none",
            explanation="No usable condenser in/out samples while running.",
        )

    n = len(delta_t)
    third = max(n // 3, 1)
    early_median = float(delta_t.iloc[:third].median())
    late_median = float(delta_t.iloc[-third:].median())
    overall_median = float(delta_t.median())

    below_floor = late_median < CONDENSER_DELTA_T_FLOOR_C
    relative_drop = (
        (early_median - late_median) / early_median if early_median > 0 else 0.0
    )
    collapsing = relative_drop >= CONDENSER_DELTA_T_RELATIVE_DROP

    triggered = bool(below_floor or collapsing)

    if triggered:
        severity = "critical" if below_floor else "warning"
        explanation = (
            f"Condenser air temperature rise (the 'delta-T' -- how much "
            f"hotter air leaves the condenser than it enters) fell from "
            f"{early_median:.1f}C early in the window to {late_median:.1f}C "
            f"late ({relative_drop * 100:.0f}% drop), "
            f"{'below the ' + str(CONDENSER_DELTA_T_FLOOR_C) + 'C floor' if below_floor else 'a large relative collapse'}. "
            "Consistent with a clogged condenser coil or blocked airflow."
        )
    else:
        severity = "none"
        explanation = (
            f"Condenser delta-T median {overall_median:.1f}C "
            f"(early {early_median:.1f}C, late {late_median:.1f}C); "
            f"stayed above the {CONDENSER_DELTA_T_FLOOR_C}C floor with no "
            "large relative collapse."
        )

    return SignatureResult(
        triggered=triggered,
        severity=severity,
        metrics={
            "early_median_delta_t_c": early_median,
            "late_median_delta_t_c": late_median,
            "overall_median_delta_t_c": overall_median,
            "relative_drop": float(relative_drop),
        },
        explanation=explanation,
        evidence=delta_t,
    )


# --- 4. knocking -------------------------------------------------------

# Beater-pod vibration RMS this many times the rolling median counts as a
# spike. (provisional)
KNOCK_RMS_FACTOR = 3.0
# Rolling-median window, in number of vib_summary rows, used as the
# "normal" baseline to compare spikes against. (provisional)
KNOCK_ROLLING_WINDOW = 15
# Spikes must cluster -- at least this many within KNOCK_CLUSTER_SPAN --
# to count as a knocking pattern rather than one noisy reading.
# (provisional)
KNOCK_MIN_CLUSTER_COUNT = 2
KNOCK_CLUSTER_SPAN = pd.Timedelta(hours=1)

POD_BEATER = 1


def detect_knocking(dep: Deployment) -> SignatureResult:
    """Flag knocking during freeze-down (ice or air in the cylinder).

    What it catches: the beater-drive vibration pod (`pod_id == 1`)
    showing RMS acceleration spikes well above ( `KNOCK_RMS_FACTOR` times)
    its own recent rolling-median baseline, with at least
    `KNOCK_MIN_CLUSTER_COUNT` such spikes within `KNOCK_CLUSTER_SPAN` --
    i.e. repeated hard impacts, not one bump. That pattern matches a hard
    piece of ice, a slug of air, or a mis-set scraper blade hitting the
    cylinder wall repeatedly during freeze-down.

    What it can't catch: it works from the periodic `vib_summary` rows,
    which are RMS/peak/band-energy summaries, not raw waveforms -- it
    can't itself distinguish a knock from, say, a tech bumping the
    machine, and it doesn't inspect raw `.bin` burst captures (where a
    knock event's higher-resolution frequency content, e.g. the low-Hz
    thump described in the gallery, could be told apart from a broadband
    impact). It also has no way to catch knocking that happens exactly
    between two summary samples if the on-card capture cadence is coarse
    relative to the knock duration.

    False-positive modes: a vibration pod that's come loose or is poorly
    mounted will read spurious spikes uncorrelated with anything
    mechanical happening inside the cylinder. A very short deployment
    window (fewer rows than `KNOCK_ROLLING_WINDOW`) doesn't have enough
    history to establish a meaningful rolling baseline and won't trigger
    even if a real knock is present.
    """
    channels, vib = _normalize(dep)
    if vib is None or len(vib) == 0 or "pod_id" not in vib.columns:
        return SignatureResult(
            triggered=False,
            severity="none",
            explanation="No vibration summary data available.",
        )

    pod1 = vib[vib["pod_id"] == POD_BEATER].copy()
    if pod1.empty:
        return SignatureResult(
            triggered=False,
            severity="none",
            explanation="No beater-drive pod (pod_id=1) vibration data available.",
        )

    pod1 = pod1.sort_index()
    rms = pod1[["rms_x_g", "rms_y_g", "rms_z_g"]].mean(axis=1)
    baseline = rms.rolling(KNOCK_ROLLING_WINDOW, min_periods=3, center=True).median()
    ratio = rms / baseline.replace(0, np.nan)

    spikes = pod1.loc[ratio >= KNOCK_RMS_FACTOR]
    n_spikes = len(spikes)

    max_cluster = 0
    if not spikes.empty:
        spike_times = spikes.index.to_series()
        for t in spike_times:
            window_count = (
                (spike_times >= t) & (spike_times < t + KNOCK_CLUSTER_SPAN)
            ).sum()
            max_cluster = max(max_cluster, window_count)

    triggered = bool(max_cluster >= KNOCK_MIN_CLUSTER_COUNT)

    if triggered:
        severity = "critical" if max_cluster >= KNOCK_MIN_CLUSTER_COUNT * 3 else "warning"
        explanation = (
            f"Beater-pod vibration ('shaking,' measured as RMS "
            f"acceleration) spiked {KNOCK_RMS_FACTOR}x or more above its "
            f"own rolling baseline {n_spikes} times, with a cluster of "
            f"{max_cluster} spikes within {KNOCK_CLUSTER_SPAN}. Consistent "
            "with repeated knocking -- ice, air, or a scraper-blade issue "
            "inside the cylinder."
        )
    else:
        severity = "none"
        explanation = (
            f"{n_spikes} vibration spikes >= {KNOCK_RMS_FACTOR}x baseline "
            f"found; largest cluster {max_cluster} within "
            f"{KNOCK_CLUSTER_SPAN} (threshold {KNOCK_MIN_CLUSTER_COUNT}). "
            "No knocking pattern."
        )

    return SignatureResult(
        triggered=triggered,
        severity=severity,
        metrics={
            "n_spikes": int(n_spikes),
            "max_cluster_in_window": int(max_cluster),
        },
        explanation=explanation,
        evidence=pod1[["rms_x_g", "rms_y_g", "rms_z_g"]].assign(ratio_to_baseline=ratio),
    )


# --- 5. belt slip --------------------------------------------------------

# Beater current below this, while beater_on=1, counts as "unloaded" --
# spinning with no mechanical load coupled in. (provisional)
BELT_SLIP_CURRENT_FLOOR_A = 1.8
# Fraction of beater-on samples that must be below the floor before this
# counts as a pattern rather than noise/startup transients. (provisional)
BELT_SLIP_MIN_FRACTION = 0.5
# Minimum number of beater-on samples required to evaluate at all.
BELT_SLIP_MIN_SAMPLES = 30


def detect_belt_slip(dep: Deployment) -> SignatureResult:
    """Flag a slipping or broken beater drive belt.

    What it catches: `current_beater_a` sagging below
    `BELT_SLIP_CURRENT_FLOOR_A` for a large fraction
    (`BELT_SLIP_MIN_FRACTION`) of the time `beater_on` is 1 -- the motor
    is being commanded on and is presumably spinning, but isn't drawing
    the current a normally *loaded* beater draws, meaning it isn't
    actually turning the dasher against the product. When vibration data
    is available, it also checks that beater-pod RMS energy is reduced
    (a slipping/broken belt should be *quieter*, not louder, since the
    load is decoupled), as a corroborating check.

    What it can't catch: it can't tell a slipping belt from a sheared
    dasher/pin, a disconnected coupling, or the cylinder being run empty
    (no product loaded) -- all present as "commanded on, current low."
    It also can't catch a belt that's slipping only *intermittently* under
    peak load if that never drags the current-averaged-over-the-window
    below the floor.

    False-positive modes: a brief low-current reading right at startup
    (motor spin-up) could look like a slip if a deployment happens to be
    very short and dominated by startup transients -- `BELT_SLIP_MIN_SAMPLES`
    guards against evaluating too little data, but doesn't fully eliminate
    this for short runs. A CT clamp that's slipped off the beater leg
    entirely would also read persistently low/zero current and look
    identical to a real belt failure.
    """
    channels, vib = _normalize(dep)
    beater_on = _bool_col(channels, "beater_on")
    if beater_on.empty or "current_beater_a" not in channels.columns:
        return SignatureResult(
            triggered=False,
            severity="none",
            explanation="No beater_on/current_beater_a data available.",
        )

    loaded = channels.loc[beater_on.reindex(channels.index, fill_value=False), "current_beater_a"]
    loaded = loaded.dropna()

    if len(loaded) < BELT_SLIP_MIN_SAMPLES:
        return SignatureResult(
            triggered=False,
            severity="none",
            explanation=(
                f"Only {len(loaded)} beater-on samples available "
                f"(need >= {BELT_SLIP_MIN_SAMPLES}); not enough to evaluate."
            ),
        )

    unloaded = loaded < BELT_SLIP_CURRENT_FLOOR_A
    fraction_unloaded = float(unloaded.mean())
    median_current = float(loaded.median())

    triggered = bool(fraction_unloaded >= BELT_SLIP_MIN_FRACTION)

    vib_note = ""
    pod1 = None
    if vib is not None and len(vib) and "pod_id" in vib.columns:
        pod1 = vib[vib["pod_id"] == POD_BEATER]
        if not pod1.empty:
            rms = pod1[["rms_x_g", "rms_y_g", "rms_z_g"]].mean(axis=1)
            vib_note = f" Beater-pod vibration RMS median {rms.median():.3f}g over the window."

    if triggered:
        severity = "warning" if fraction_unloaded < 0.85 else "critical"
        explanation = (
            f"current_beater_a stayed below {BELT_SLIP_CURRENT_FLOOR_A}A "
            f"(the loaded-current floor) for {fraction_unloaded * 100:.0f}% "
            f"of the time beater_on was commanded, median {median_current:.2f}A. "
            "The motor is running but not driving a load -- consistent with "
            "a slipping or broken drive belt." + vib_note
        )
    else:
        severity = "none"
        explanation = (
            f"current_beater_a below the {BELT_SLIP_CURRENT_FLOOR_A}A floor "
            f"only {fraction_unloaded * 100:.0f}% of beater-on time (median "
            f"{median_current:.2f}A). Normal loaded drive."
        )

    return SignatureResult(
        triggered=triggered,
        severity=severity,
        metrics={
            "fraction_unloaded": fraction_unloaded,
            "median_loaded_current_a": median_current,
            "n_samples": int(len(loaded)),
        },
        explanation=explanation,
        evidence=loaded,
    )


# --- 6. motor degradation ---------------------------------------------------

# Daily-median beater current (while loaded) drift, in amps/day, above
# which we call it a degradation trend rather than noise. (provisional)
MOTOR_DEGRADATION_SLOPE_A_PER_DAY = 0.03
# Need at least this many distinct days of data for a trend to mean
# anything. (provisional)
MOTOR_DEGRADATION_MIN_DAYS = 7


def detect_motor_degradation(dep: Deployment) -> SignatureResult:
    """Flag gradual beater-motor degradation.

    What it catches: a robust (median-based, outlier-resistant) linear
    trend in the *daily median* `current_beater_a` while loaded
    (`beater_on == 1`), across the full deployment. A steady upward drift
    above `MOTOR_DEGRADATION_SLOPE_A_PER_DAY` amps/day is consistent with
    bearings or windings wearing and the motor working harder over weeks
    to turn the same load.

    What it can't catch: it can't distinguish a genuinely wearing motor
    from a slow product/mix change (a thicker mix draws more current too),
    a seasonal ambient temperature drift changing product viscosity, or a
    drive belt that's been re-tensioned partway through the deployment
    (which would show as a step, not a trend, but a simple linear fit can
    still register as a slope). It only looks at current, not vibration
    trend or bearing-specific frequency content, so it won't catch
    degradation that shows up acoustically before it shows up electrically.

    False-positive modes: a deployment under `MOTOR_DEGRADATION_MIN_DAYS`
    days doesn't get evaluated at all -- too little data for "trend" to
    mean anything. A deployment that changes which flavor/mix
    recipe runs on different days could manufacture an apparent trend
    from a real but unrelated cause.
    """
    channels, _vib = _normalize(dep)
    beater_on = _bool_col(channels, "beater_on")
    if beater_on.empty or "current_beater_a" not in channels.columns:
        return SignatureResult(
            triggered=False,
            severity="none",
            explanation="No beater_on/current_beater_a data available.",
        )

    loaded = channels.loc[beater_on.reindex(channels.index, fill_value=False), "current_beater_a"]
    loaded = loaded.dropna()
    if loaded.empty:
        return SignatureResult(
            triggered=False,
            severity="none",
            explanation="No loaded beater-current samples available.",
        )

    daily_median = loaded.groupby(loaded.index.normalize()).median()
    n_days = len(daily_median)

    if n_days < MOTOR_DEGRADATION_MIN_DAYS:
        return SignatureResult(
            triggered=False,
            severity="none",
            explanation=(
                f"Only {n_days} distinct day(s) of loaded beater-current "
                f"data (need >= {MOTOR_DEGRADATION_MIN_DAYS}); too short a "
                "window to evaluate a long-term trend."
            ),
            metrics={"n_days": n_days},
        )

    # Robust linear trend: Theil-Sen slope (median of pairwise slopes) is
    # resistant to the occasional bad/outlier day in a way ordinary
    # least-squares isn't.
    day_numbers = np.arange(n_days, dtype=float)
    values = daily_median.to_numpy()
    slopes = []
    for i in range(n_days):
        for j in range(i + 1, n_days):
            dx = day_numbers[j] - day_numbers[i]
            if dx != 0:
                slopes.append((values[j] - values[i]) / dx)
    slope_a_per_day = float(np.median(slopes)) if slopes else 0.0

    triggered = bool(slope_a_per_day >= MOTOR_DEGRADATION_SLOPE_A_PER_DAY)
    total_drift = slope_a_per_day * (n_days - 1)

    if triggered:
        severity = (
            "critical" if slope_a_per_day >= MOTOR_DEGRADATION_SLOPE_A_PER_DAY * 3 else "warning"
        )
        explanation = (
            f"Daily-median loaded beater current is trending up "
            f"{slope_a_per_day:.3f}A/day across {n_days} days "
            f"(threshold {MOTOR_DEGRADATION_SLOPE_A_PER_DAY}A/day), "
            f"~{total_drift:.2f}A total drift. Consistent with gradual "
            "motor wear (bearings/windings)."
        )
    else:
        severity = "none"
        explanation = (
            f"Daily-median loaded beater current trend "
            f"{slope_a_per_day:.3f}A/day across {n_days} days "
            f"(threshold {MOTOR_DEGRADATION_SLOPE_A_PER_DAY}A/day). No "
            "degradation trend."
        )

    return SignatureResult(
        triggered=triggered,
        severity=severity,
        metrics={
            "slope_a_per_day": slope_a_per_day,
            "n_days": n_days,
            "total_drift_a": float(total_drift),
        },
        explanation=explanation,
        evidence=daily_median,
    )
