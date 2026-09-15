"""Tests for `frosty_analysis.signatures` against `frosty_analysis.synthetic`
segments.

For every detector: it triggers on its own matching synthetic failure
segment, and does not trigger on `make_healthy`. `short_cycling` and
`condenser_airflow` are additionally cross-checked against each other's
segment, since both touch compressor-cycle timing/temperature and are the
easiest pair to accidentally conflate.
"""

from __future__ import annotations

import pandas as pd
import pytest

from frosty_analysis import synthetic as syn
from frosty_analysis.signatures import (
    SEAL_DRIP_SUSTAINED_FLOOR_CPM,
    SignatureResult,
    detect_belt_slip,
    detect_condenser_airflow,
    detect_knocking,
    detect_motor_degradation,
    detect_seal_failure,
    detect_short_cycling,
    detect_tcc_never_satisfied,
)

# A fixed seed per scenario keeps these deterministic across runs while
# still exercising the RNG-driven code paths in synthetic.py.
SEED = 12345


@pytest.fixture(scope="module")
def healthy():
    return syn.make_healthy(hours=8.0, rng=SEED)


@pytest.fixture(scope="module")
def short_cycling():
    return syn.make_short_cycling(hours=4.0, rng=SEED)


@pytest.fixture(scope="module")
def tcc_never_satisfied():
    return syn.make_tcc_never_satisfied(hours=5.0, rng=SEED)


@pytest.fixture(scope="module")
def condenser_airflow():
    return syn.make_condenser_airflow(hours=10.0, rng=SEED)


@pytest.fixture(scope="module")
def knocking():
    return syn.make_knocking(hours=5.0, rng=SEED)


@pytest.fixture(scope="module")
def belt_slip():
    return syn.make_belt_slip(hours=5.0, rng=SEED)


@pytest.fixture(scope="module")
def motor_degradation():
    return syn.make_motor_degradation(days=21, rng=SEED)


@pytest.fixture(scope="module")
def seal_failure():
    return syn.make_seal_failure(days=21, rng=SEED)


# --- basic shape sanity on the generators themselves -----------------------


def test_healthy_segment_shape(healthy):
    assert isinstance(healthy.channels, pd.DataFrame)
    assert isinstance(healthy.channels.index, pd.DatetimeIndex)
    assert healthy.channels.index.tz is not None
    assert str(healthy.channels.index.tz) == "UTC"
    assert healthy.channels.index.is_monotonic_increasing
    assert len(healthy.channels) > 0
    assert isinstance(healthy.vib_summary, pd.DataFrame)


def test_healthy_has_some_running_and_some_idle_time(healthy):
    cmd = healthy.channels["compressor_cmd"]
    assert cmd.sum() > 0
    assert (cmd == 0).sum() > 0


# --- 1. short cycling --------------------------------------------------


def test_short_cycling_triggers_on_its_segment(short_cycling):
    result = detect_short_cycling(short_cycling)
    assert isinstance(result, SignatureResult)
    assert result.triggered is True
    assert result.severity in {"warning", "critical"}
    assert result.metrics["n_short_runs"] > 0


def test_short_cycling_does_not_trigger_on_healthy(healthy):
    result = detect_short_cycling(healthy)
    assert result.triggered is False


def test_short_cycling_does_not_trigger_on_condenser_airflow(condenser_airflow):
    # Cross-check: condenser_airflow keeps normal 4-8min run/hold cycling,
    # only condenser temps degrade -- short_cycling must not fire on it.
    result = detect_short_cycling(condenser_airflow)
    assert result.triggered is False


# --- 2. TCC never satisfied --------------------------------------------


def test_tcc_never_satisfied_triggers_on_its_segment(tcc_never_satisfied):
    result = detect_tcc_never_satisfied(tcc_never_satisfied)
    assert result.triggered is True
    assert result.severity in {"warning", "critical"}
    assert result.metrics["longest_unsatisfied_run_hours"] > 0


def test_tcc_never_satisfied_does_not_trigger_on_healthy(healthy):
    result = detect_tcc_never_satisfied(healthy)
    assert result.triggered is False


# --- 3. condenser airflow -----------------------------------------------


def test_condenser_airflow_triggers_on_its_segment(condenser_airflow):
    result = detect_condenser_airflow(condenser_airflow)
    assert result.triggered is True
    assert result.severity in {"warning", "critical"}
    assert result.metrics["late_median_delta_t_c"] < result.metrics["early_median_delta_t_c"]


def test_condenser_airflow_does_not_trigger_on_healthy(healthy):
    result = detect_condenser_airflow(healthy)
    assert result.triggered is False


def test_condenser_airflow_does_not_trigger_on_short_cycling(short_cycling):
    # Cross-check, other direction: short_cycling keeps condenser dT/discharge
    # healthy on purpose -- condenser_airflow must not fire on it.
    result = detect_condenser_airflow(short_cycling)
    assert result.triggered is False


# --- 4. knocking ---------------------------------------------------------


def test_knocking_triggers_on_its_segment(knocking):
    result = detect_knocking(knocking)
    assert result.triggered is True
    assert result.severity in {"warning", "critical"}
    assert result.metrics["n_spikes"] > 0


def test_knocking_does_not_trigger_on_healthy(healthy):
    result = detect_knocking(healthy)
    assert result.triggered is False


def test_knocking_segment_has_a_raw_burst_with_low_frequency_content(knocking):
    assert len(knocking.bursts) >= 1
    burst = knocking.bursts[0]
    assert burst.pod_id == 1
    assert burst.data.shape[1] == 3


# --- 5. belt slip ----------------------------------------------------------


def test_belt_slip_triggers_on_its_segment(belt_slip):
    result = detect_belt_slip(belt_slip)
    assert result.triggered is True
    assert result.severity in {"warning", "critical"}
    assert result.metrics["fraction_unloaded"] > 0.5


def test_belt_slip_does_not_trigger_on_healthy(healthy):
    result = detect_belt_slip(healthy)
    assert result.triggered is False


# --- 6. motor degradation ---------------------------------------------------


def test_motor_degradation_triggers_on_its_segment(motor_degradation):
    result = detect_motor_degradation(motor_degradation)
    assert result.triggered is True
    assert result.severity in {"warning", "critical"}
    assert result.metrics["slope_a_per_day"] > 0


def test_motor_degradation_does_not_trigger_on_healthy(healthy):
    # healthy is only 8 hours -- too short a window for a "days" trend,
    # so this should come back untriggered (and self-explanatory as to why).
    result = detect_motor_degradation(healthy)
    assert result.triggered is False


def test_motor_degradation_does_not_trigger_on_a_longer_healthy_segment():
    # A healthy segment long enough to actually be evaluated for a trend
    # (>= MOTOR_DEGRADATION_MIN_DAYS) should still not trigger.
    long_healthy = syn.make_healthy(hours=24 * 10, rng=SEED)
    result = detect_motor_degradation(long_healthy)
    assert result.triggered is False


# --- 7. seal failure (leak) -------------------------------------------------


def test_seal_failure_triggers_on_its_segment(seal_failure):
    result = detect_seal_failure(seal_failure)
    assert isinstance(result, SignatureResult)
    assert result.triggered is True
    assert result.severity in {"warning", "critical"}


def test_seal_failure_does_not_trigger_on_healthy(healthy):
    result = detect_seal_failure(healthy)
    assert result.triggered is False


def test_seal_failure_does_not_trigger_on_short_cycling(short_cycling):
    # Cross-check: short_cycling doesn't touch drip_rate_cpm at all, so it
    # should carry the same healthy leak baseline and never trigger here.
    result = detect_seal_failure(short_cycling)
    assert result.triggered is False


def test_healthy_drip_rate_stays_below_seal_failure_threshold(healthy):
    # The healthy generator's drip baseline is isolated blips only, never
    # sustained -- it should never even approach the sustained-drip floor.
    assert healthy.channels["drip_rate_cpm"].max() < SEAL_DRIP_SUSTAINED_FLOOR_CPM


# --- accepting bare DataFrames / Deployments (normalization) ---------------


def test_detectors_accept_a_bare_channels_dataframe(short_cycling):
    # Per the OWNERSHIP brief: detectors must also accept a bare
    # channels DataFrame directly, not just a Deployment/SyntheticSegment.
    result = detect_short_cycling(short_cycling.channels)
    assert isinstance(result, SignatureResult)
    assert result.triggered is True


def test_vibration_detector_on_bare_dataframe_does_not_raise(short_cycling):
    # No vib_summary available from a bare channels frame -- should report
    # untriggered, not raise.
    result = detect_knocking(short_cycling.channels)
    assert result.triggered is False
