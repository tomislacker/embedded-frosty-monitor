"""Readers for the on-card frosty-monitor data format v1.

See ``docs/firmware/data-format-spec.md`` in the repo root for the
authoritative, canonical description of the on-card layout. This module
builds to that spec; if the two disagree, the spec wins.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

CHANNELS_COLUMNS = [
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

VIB_SUMMARY_COLUMNS = [
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

EVENTS_COLUMNS = ["ts_iso", "ts_unix_ms", "type", "detail"]

# Little-endian packed 32-byte burst header, per data-format-spec.md:
#   magic(4s) format_version(B) pod_id(B) reserved(H)
#   sample_rate_hz(I) n_samples(I) n_axes(B) reserved(3s)
#   start_ts_unix_ms(Q) scale_g_per_lsb(f)
_BURST_HEADER_FORMAT = "<4sBBHIIB3sQf"
_BURST_HEADER_SIZE = struct.calcsize(_BURST_HEADER_FORMAT)
_BURST_MAGIC = b"FVB1"
_BURST_FORMAT_VERSION = 1


@dataclass
class Deployment:
    """In-memory representation of one deployment's worth of card data."""

    manifest: dict
    channels: pd.DataFrame
    vib_summary: pd.DataFrame
    events: pd.DataFrame
    burst_files: list[Path] = field(default_factory=list)


@dataclass
class VibrationBurst:
    """One decoded ``vib_<pod>_<ts_unix_ms>.bin`` capture."""

    pod_id: int
    sample_rate_hz: int
    start_ts: pd.Timestamp
    scale_g_per_lsb: float
    data: np.ndarray  # shape (n_samples, 3), float64, g


def _empty_channels() -> pd.DataFrame:
    df = pd.DataFrame(columns=CHANNELS_COLUMNS)
    df.index = pd.DatetimeIndex([], tz="UTC", name="ts")
    return df.drop(columns=["ts_iso"])


def _empty_vib_summary() -> pd.DataFrame:
    df = pd.DataFrame(columns=VIB_SUMMARY_COLUMNS)
    df.index = pd.DatetimeIndex([], tz="UTC", name="ts")
    return df.drop(columns=["ts_iso"])


def _empty_events() -> pd.DataFrame:
    df = pd.DataFrame(columns=EVENTS_COLUMNS)
    df.index = pd.DatetimeIndex([], tz="UTC", name="ts")
    return df.drop(columns=["ts_iso"])


def _load_channel_csvs(paths: list[Path]) -> pd.DataFrame:
    if not paths:
        return _empty_channels()
    frames = []
    for p in sorted(paths):
        # Read by name so unknown trailing columns (future firmware
        # versions may append them, per data-format-spec.md) are carried
        # along rather than breaking the read.
        frame = pd.read_csv(p)
        frames.append(frame)
    df = pd.concat(frames, ignore_index=True)
    ts = pd.to_datetime(df["ts_iso"], utc=True)
    df = df.drop(columns=["ts_iso"])
    df.index = pd.DatetimeIndex(ts, name="ts")
    df = df.sort_index()
    return df


def _load_vib_summary_csvs(paths: list[Path]) -> pd.DataFrame:
    if not paths:
        return _empty_vib_summary()
    frames = [pd.read_csv(p) for p in sorted(paths)]
    df = pd.concat(frames, ignore_index=True)
    ts = pd.to_datetime(df["ts_iso"], utc=True)
    df = df.drop(columns=["ts_iso"])
    df.index = pd.DatetimeIndex(ts, name="ts")
    df = df.sort_index()
    return df


def _load_event_jsonl(paths: list[Path]) -> pd.DataFrame:
    if not paths:
        return _empty_events()
    records = []
    for p in sorted(paths):
        with open(p, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
    if not records:
        return _empty_events()
    df = pd.DataFrame.from_records(records, columns=EVENTS_COLUMNS)
    ts = pd.to_datetime(df["ts_iso"], utc=True)
    df = df.drop(columns=["ts_iso"])
    df.index = pd.DatetimeIndex(ts, name="ts")
    df = df.sort_index()
    return df


def load_deployment(path: str | Path) -> Deployment:
    """Load one deployment's card dump directory into a `Deployment`.

    Tolerates missing pieces (no events file, no vibration directory,
    a single day of data): the corresponding field comes back as an empty
    DataFrame with the correct columns rather than raising.
    """
    root = Path(path)

    manifest_path = root / "manifest.json"
    manifest: dict = {}
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)

    channel_paths = sorted(root.glob("channels_*.csv"))
    channels = _load_channel_csvs(channel_paths)

    event_paths = sorted(root.glob("events_*.jsonl"))
    events = _load_event_jsonl(event_paths)

    vib_dir = root / "vibration"
    if vib_dir.is_dir():
        vib_summary_paths = sorted(vib_dir.glob("vib_summary_*.csv"))
        vib_summary = _load_vib_summary_csvs(vib_summary_paths)
        burst_files = sorted(vib_dir.glob("vib_*.bin"))
    else:
        vib_summary = _empty_vib_summary()
        burst_files = []

    return Deployment(
        manifest=manifest,
        channels=channels,
        vib_summary=vib_summary,
        events=events,
        burst_files=burst_files,
    )


def load_vibration_burst(path: str | Path) -> VibrationBurst:
    """Decode one ``vib_<pod>_<ts_unix_ms>.bin`` burst capture file.

    Raises `ValueError` with a clear message if the magic bytes or format
    version don't match what this reader understands.
    """
    p = Path(path)
    raw = p.read_bytes()

    if len(raw) < _BURST_HEADER_SIZE:
        raise ValueError(
            f"{p}: file is only {len(raw)} bytes, shorter than the "
            f"{_BURST_HEADER_SIZE}-byte burst header"
        )

    (
        magic,
        format_version,
        pod_id,
        _reserved1,
        sample_rate_hz,
        n_samples,
        n_axes,
        _reserved2,
        start_ts_unix_ms,
        scale_g_per_lsb,
    ) = struct.unpack(_BURST_HEADER_FORMAT, raw[:_BURST_HEADER_SIZE])

    if magic != _BURST_MAGIC:
        raise ValueError(
            f"{p}: bad magic {magic!r}, expected {_BURST_MAGIC!r} "
            "(not a vibration burst file?)"
        )
    if format_version != _BURST_FORMAT_VERSION:
        raise ValueError(
            f"{p}: unsupported format_version {format_version}, "
            f"this reader only understands version {_BURST_FORMAT_VERSION}"
        )

    expected_payload_bytes = n_samples * n_axes * 2  # int16 = 2 bytes
    payload = raw[_BURST_HEADER_SIZE:]
    if len(payload) < expected_payload_bytes:
        raise ValueError(
            f"{p}: payload is {len(payload)} bytes, expected "
            f"{expected_payload_bytes} for n_samples={n_samples}, "
            f"n_axes={n_axes}"
        )

    raw_samples = np.frombuffer(
        payload[:expected_payload_bytes], dtype="<i2"
    ).reshape(n_samples, n_axes)
    data = raw_samples.astype(np.float64) * scale_g_per_lsb

    start_ts = pd.Timestamp(start_ts_unix_ms, unit="ms", tz="UTC")

    return VibrationBurst(
        pod_id=pod_id,
        sample_rate_hz=sample_rate_hz,
        start_ts=start_ts,
        scale_g_per_lsb=scale_g_per_lsb,
        data=data,
    )
