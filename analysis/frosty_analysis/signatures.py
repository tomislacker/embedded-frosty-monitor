"""Failure-signature detectors.

Roadmap stubs only — see ``docs/roadmap.md`` item 2 ("Signature-detection
implementations in analysis"). Each function documents the intended
detection logic but is not yet implemented; calling it raises
`NotImplementedError`.
"""

from __future__ import annotations

from frosty_analysis.loader import Deployment


def detect_short_cycling(dep: Deployment) -> None:
    """Flag compressor short-cycling.

    Intended logic: derive on/off run lengths from `compressor_cmd`
    transitions in `dep.channels`, and flag periods where cycle durations
    are consistently under ~30s and clustered close together in time,
    rather than a single isolated short cycle (which can be a normal
    startup blip).
    """
    raise NotImplementedError("roadmap: see docs/roadmap.md")


def detect_tcc_never_satisfied(dep: Deployment) -> None:
    """Flag a "won't freeze" condition.

    Intended logic: look for extended runs where `compressor_cmd` and
    `beater_on` are both 1 for far longer than a normal freeze-down cycle
    while `tcc_satisfied` never transitions to 1, suggesting the machine is
    running continuously without ever reaching the thermostatic cut-out
    setpoint.
    """
    raise NotImplementedError("roadmap: see docs/roadmap.md")


def detect_condenser_airflow(dep: Deployment) -> None:
    """Flag clogged condenser / poor ventilation.

    Intended logic: while `compressor_cmd` is 1, compute the condenser air
    delta-T (`temp_cond_out_c` - `temp_cond_in_c`) and flag periods where
    that delta is abnormally low alongside an elevated
    `temp_discharge_c`, which together indicate the condenser isn't
    rejecting heat effectively.
    """
    raise NotImplementedError("roadmap: see docs/roadmap.md")


def detect_knocking(dep: Deployment) -> None:
    """Flag knocking during freeze-down (ice or air in the cylinder).

    Intended logic: inspect beater-drive pod (`pod_id == 1`) vibration
    bursts for transient high-amplitude impulses concentrated in the
    `band_mid_g2`/`band_high_g2` bands of `dep.vib_summary`, correlated
    with the freeze-down portion of the compressor cycle rather than
    steady running.
    """
    raise NotImplementedError("roadmap: see docs/roadmap.md")


def detect_belt_slip(dep: Deployment) -> None:
    """Flag belt loss or slip on the beater drive.

    Intended logic: look for `current_beater_a` sagging or oscillating
    below its normal loaded range while `beater_on` is 1, optionally cross
    -checked against reduced beater-drive pod vibration energy
    (`rms_*_g` in `dep.vib_summary` for `pod_id == 1`), which would
    indicate the motor is spinning with little mechanical load.
    """
    raise NotImplementedError("roadmap: see docs/roadmap.md")


def detect_motor_degradation(dep: Deployment) -> None:
    """Flag gradual motor degradation.

    Intended logic: track long-term trends in steady-state
    `current_beater_a`/`current_compressor_a` draw and vibration RMS
    envelopes across the full deployment, flagging a slow upward drift
    relative to the deployment's early baseline as bearings or windings
    wear.
    """
    raise NotImplementedError("roadmap: see docs/roadmap.md")
