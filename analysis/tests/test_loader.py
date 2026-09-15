from __future__ import annotations

import shutil
import struct
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pandas as pd
import pytest

from frosty_analysis import load_deployment, load_vibration_burst
from frosty_analysis.loader import CHANNELS_COLUMNS, EVENTS_COLUMNS, VIB_SUMMARY_COLUMNS
from frosty_analysis.plots import (
    plot_burst_spectrogram,
    plot_burst_waveform,
    plot_channels,
    plot_state_timeline,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample_deployment"


@pytest.fixture(scope="module")
def deployment():
    return load_deployment(FIXTURE_DIR)


# --- full-deployment load -------------------------------------------------


def test_channels_row_count_across_two_days(deployment):
    # 600 rows/day * 2 days, per make_fixture.py's ROWS_PER_DAY.
    assert len(deployment.channels) == 1200


def test_channels_index_is_tz_aware_utc_and_sorted(deployment):
    idx = deployment.channels.index
    assert isinstance(idx, pd.DatetimeIndex)
    assert idx.tz is not None
    assert str(idx.tz) == "UTC"
    assert idx.is_monotonic_increasing


def test_channels_has_expected_columns(deployment):
    expected = [c for c in CHANNELS_COLUMNS if c != "ts_iso"]
    assert list(deployment.channels.columns) == expected


def test_hopper_column_is_all_nan(deployment):
    assert deployment.channels["temp_hopper_c"].isna().all()


def test_discharge_column_has_some_nan(deployment):
    # make_fixture.py deliberately drops a handful of discharge samples.
    assert deployment.channels["temp_discharge_c"].isna().sum() > 0
    assert deployment.channels["temp_discharge_c"].isna().sum() < len(deployment.channels)


def test_events_parsed(deployment):
    assert len(deployment.events) == 5
    assert set(deployment.events["type"]) <= {"button", "system", "trigger", "error"}
    assert isinstance(deployment.events.index, pd.DatetimeIndex)
    assert deployment.events.index.tz is not None
    # detail should come through as a dict, not a JSON string.
    assert isinstance(deployment.events["detail"].iloc[0], dict)


def test_manifest_fields(deployment):
    assert deployment.manifest["schema_version"] == 1
    assert deployment.manifest["machine_model"] == "137A"


def test_burst_files_found(deployment):
    assert len(deployment.burst_files) == 2
    assert all(p.suffix == ".bin" for p in deployment.burst_files)
    assert deployment.burst_files == sorted(deployment.burst_files)


def test_vib_summary_loaded(deployment):
    assert len(deployment.vib_summary) == 20
    expected = [c for c in VIB_SUMMARY_COLUMNS if c != "ts_iso"]
    assert list(deployment.vib_summary.columns) == expected
    assert isinstance(deployment.vib_summary.index, pd.DatetimeIndex)


# --- burst load ------------------------------------------------------------


def test_load_vibration_burst_shape_and_dtype(deployment):
    burst = load_vibration_burst(deployment.burst_files[0])
    assert burst.data.shape == (800, 3)
    assert burst.data.dtype == np.float64
    assert burst.sample_rate_hz == 1600


def test_load_vibration_burst_pod_ids(deployment):
    pod_ids = {load_vibration_burst(p).pod_id for p in deployment.burst_files}
    assert pod_ids == {1, 2}


def test_load_vibration_burst_bad_magic_raises(tmp_path):
    bad_path = tmp_path / "vib_1_1234567890000.bin"
    header = struct.pack(
        "<4sBBHIIB3sQf",
        b"XXXX",  # wrong magic
        1,
        1,
        0,
        1600,
        800,
        3,
        b"\x00\x00\x00",
        1234567890000,
        0.004,
    )
    bad_path.write_bytes(header + bytes(800 * 3 * 2))
    with pytest.raises(ValueError, match="magic"):
        load_vibration_burst(bad_path)


def test_load_vibration_burst_bad_version_raises(tmp_path):
    bad_path = tmp_path / "vib_1_1234567890000.bin"
    header = struct.pack(
        "<4sBBHIIB3sQf",
        b"FVB1",
        7,  # unsupported format_version
        1,
        0,
        1600,
        800,
        3,
        b"\x00\x00\x00",
        1234567890000,
        0.004,
    )
    bad_path.write_bytes(header + bytes(800 * 3 * 2))
    with pytest.raises(ValueError, match="format_version"):
        load_vibration_burst(bad_path)


# --- partial-deployment tolerance ------------------------------------------


def test_partial_deployment_missing_events_and_vibration(tmp_path):
    partial_dir = tmp_path / "partial_deployment"
    partial_dir.mkdir()
    shutil.copy(FIXTURE_DIR / "manifest.json", partial_dir / "manifest.json")
    for csv in FIXTURE_DIR.glob("channels_*.csv"):
        shutil.copy(csv, partial_dir / csv.name)
    # deliberately omit events_*.jsonl and vibration/

    dep = load_deployment(partial_dir)

    assert len(dep.channels) == 1200
    assert isinstance(dep.events, pd.DataFrame)
    assert len(dep.events) == 0
    assert list(dep.events.columns) == [c for c in EVENTS_COLUMNS if c != "ts_iso"]

    assert isinstance(dep.vib_summary, pd.DataFrame)
    assert len(dep.vib_summary) == 0
    assert list(dep.vib_summary.columns) == [c for c in VIB_SUMMARY_COLUMNS if c != "ts_iso"]

    assert dep.burst_files == []


def test_partial_deployment_single_day(tmp_path):
    partial_dir = tmp_path / "single_day_deployment"
    partial_dir.mkdir()
    shutil.copy(FIXTURE_DIR / "manifest.json", partial_dir / "manifest.json")
    day1_csv = sorted(FIXTURE_DIR.glob("channels_*.csv"))[0]
    shutil.copy(day1_csv, partial_dir / day1_csv.name)

    dep = load_deployment(partial_dir)

    assert len(dep.channels) == 600


def test_empty_deployment_directory(tmp_path):
    empty_dir = tmp_path / "empty_deployment"
    empty_dir.mkdir()

    dep = load_deployment(empty_dir)

    assert dep.manifest == {}
    assert len(dep.channels) == 0
    assert len(dep.events) == 0
    assert len(dep.vib_summary) == 0
    assert dep.burst_files == []


# --- plot smoke tests --------------------------------------------------


def test_plot_channels_smoke(deployment):
    fig, _axes = plot_channels(deployment)
    assert fig is not None


def test_plot_state_timeline_smoke(deployment):
    fig, _ax = plot_state_timeline(deployment)
    assert fig is not None


def test_plot_burst_waveform_smoke(deployment):
    burst = load_vibration_burst(deployment.burst_files[0])
    fig, _ax = plot_burst_waveform(burst)
    assert fig is not None


def test_plot_burst_spectrogram_smoke(deployment):
    burst = load_vibration_burst(deployment.burst_files[0])
    fig, _ax = plot_burst_spectrogram(burst)
    assert fig is not None
