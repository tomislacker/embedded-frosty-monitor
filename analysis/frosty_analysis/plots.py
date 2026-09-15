"""Diagnostic plots for a loaded `Deployment` / `VibrationBurst`.

Pure matplotlib (no seaborn), no `plt.show()` inside any function — callers
decide how/whether to render. Colors and mark specs follow the project's
dataviz skill conventions: a fixed-order categorical palette (never cycled),
a single-hue sequential ramp for magnitude (spectrogram power), thin 2px
lines, a legend whenever more than one series shares an axis, and recessive
gridlines/axis chrome so the data reads first.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from scipy import signal

from frosty_analysis.loader import Deployment, VibrationBurst

# --- dataviz skill palette (light mode) -------------------------------
CATEGORICAL = [
    "#2a78d6",  # 1 blue
    "#eb6834",  # 2 orange
    "#1baf7a",  # 3 aqua
    "#eda100",  # 4 yellow
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 green
    "#4a3aa7",  # 7 violet
    "#e34948",  # 8 red
]

CHART_SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
AXIS_BASELINE = "#c3c2b7"

_SEQUENTIAL_BLUE_STEPS = [
    "#cde2fb",
    "#b7d3f6",
    "#9ec5f4",
    "#86b6ef",
    "#6da7ec",
    "#5598e7",
    "#3987e5",
    "#2a78d6",
    "#256abf",
    "#1c5cab",
    "#184f95",
    "#104281",
    "#0d366b",
]
SEQUENTIAL_BLUE_CMAP = LinearSegmentedColormap.from_list(
    "frosty_seq_blue", _SEQUENTIAL_BLUE_STEPS
)

_LINEWIDTH = 1.5

# Unit label + categorical color, keyed by channel column name.
_CHANNEL_META: dict[str, tuple[str, str]] = {
    "current_beater_a": ("A", CATEGORICAL[0]),
    "current_compressor_a": ("A", CATEGORICAL[1]),
    "temp_cylinder_c": ("°C", CATEGORICAL[2]),
    "temp_cond_in_c": ("°C", CATEGORICAL[3]),
    "temp_cond_out_c": ("°C", CATEGORICAL[4]),
    "temp_ambient_c": ("°C", CATEGORICAL[5]),
    "temp_hopper_c": ("°C", CATEGORICAL[6]),
    "temp_discharge_c": ("°C", CATEGORICAL[7]),
}

DEFAULT_CHANNEL_COLUMNS = [
    "current_beater_a",
    "current_compressor_a",
    "temp_cylinder_c",
    "temp_discharge_c",
]

_STATE_COLUMNS = ["beater_on", "compressor_cmd", "tcc_satisfied", "hp_ok"]

_AXIS_LABELS = ("x", "y", "z")


def _style_axes(ax: Axes) -> None:
    ax.set_facecolor(CHART_SURFACE)
    ax.grid(True, color=GRIDLINE, linewidth=0.8, alpha=0.9)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(AXIS_BASELINE)
    ax.tick_params(colors=INK_MUTED, labelsize=8)
    ax.xaxis.label.set_color(INK_PRIMARY)
    ax.yaxis.label.set_color(INK_PRIMARY)
    ax.title.set_color(INK_PRIMARY)


def _channel_unit_group(column: str) -> str:
    unit, _color = _CHANNEL_META.get(column, ("value", CATEGORICAL[0]))
    return unit


def plot_channels(
    dep: Deployment, columns: list[str] | None = None, ax: Axes | None = None
) -> tuple[Figure, Axes | np.ndarray]:
    """Time-series plot of selected channel columns.

    Defaults to beater/compressor current plus key temperatures
    (cylinder jacket, discharge line). If `ax` is given, all selected
    columns are drawn onto that single axes (units noted in each legend
    label). Otherwise columns are grouped by unit into small-multiple
    subplots sharing a time axis, since mixing amps and degrees-C on one
    y-scale is misleading (never a dual y-axis).
    """
    if columns is None:
        columns = DEFAULT_CHANNEL_COLUMNS
    columns = [c for c in columns if c in dep.channels.columns]

    def _draw(target_ax: Axes, cols: list[str]) -> None:
        for col in cols:
            unit, color = _CHANNEL_META.get(col, ("value", CATEGORICAL[0]))
            target_ax.plot(
                dep.channels.index,
                dep.channels[col],
                label=f"{col} ({unit})",
                color=color,
                linewidth=_LINEWIDTH,
            )
        _style_axes(target_ax)
        target_ax.set_xlabel("time (UTC)")
        target_ax.legend(frameon=False, fontsize=8, labelcolor=INK_SECONDARY)

    if ax is not None:
        _draw(ax, columns)
        ax.set_ylabel("value")
        fig = ax.figure
        return fig, ax

    groups: dict[str, list[str]] = {}
    for col in columns:
        groups.setdefault(_channel_unit_group(col), []).append(col)

    n = max(len(groups), 1)
    fig, axes = plt.subplots(
        n, 1, sharex=True, figsize=(9, 2.6 * n), facecolor=CHART_SURFACE
    )
    axes = np.atleast_1d(axes)
    for group_ax, (unit, cols) in zip(axes, groups.items()):
        _draw(group_ax, cols)
        group_ax.set_ylabel(unit)
    axes[-1].set_xlabel("time (UTC)")
    fig.tight_layout()
    return fig, axes


def plot_state_timeline(dep: Deployment, ax: Axes | None = None) -> tuple[Figure, Axes]:
    """Plot the four boolean state channels as filled lanes over time.

    Each channel gets its own horizontal lane (direct-labeled on the
    y-axis, not color-alone) that fills solid while the value is 1.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(9, 3.2), facecolor=CHART_SURFACE)
    else:
        fig = ax.figure

    lane_height = 0.8
    for i, col in enumerate(_STATE_COLUMNS):
        color = CATEGORICAL[i % len(CATEGORICAL)]
        if col in dep.channels.columns and len(dep.channels) > 0:
            values = dep.channels[col].fillna(0).to_numpy()
            ax.fill_between(
                dep.channels.index,
                i,
                i + lane_height * values,
                step="post",
                color=color,
                linewidth=0,
            )
        ax.axhline(i, color=AXIS_BASELINE, linewidth=0.6)

    _style_axes(ax)
    ax.set_yticks([i + lane_height / 2 for i in range(len(_STATE_COLUMNS))])
    ax.set_yticklabels(_STATE_COLUMNS)
    ax.set_ylim(-0.2, len(_STATE_COLUMNS) - 1 + lane_height + 0.2)
    ax.set_xlabel("time (UTC)")
    ax.set_ylabel("state channel")
    return fig, ax


def _resolve_axis_index(axis: str | int) -> int:
    if isinstance(axis, int):
        return axis
    try:
        return _AXIS_LABELS.index(axis.lower())
    except ValueError as exc:
        raise ValueError(
            f"axis must be one of {_AXIS_LABELS!r} or an int index, got {axis!r}"
        ) from exc


def plot_burst_spectrogram(
    burst: VibrationBurst, axis: str = "z", ax: Axes | None = None
) -> tuple[Figure, Axes]:
    """Spectrogram of one axis of a vibration burst, log-scaled power."""
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 4), facecolor=CHART_SURFACE)
    else:
        fig = ax.figure

    axis_idx = _resolve_axis_index(axis)
    samples = burst.data[:, axis_idx]

    freqs, times, sxx = signal.spectrogram(samples, fs=burst.sample_rate_hz)
    sxx_db = 10 * np.log10(np.maximum(sxx, np.finfo(float).tiny))

    mesh = ax.pcolormesh(times, freqs, sxx_db, cmap=SEQUENTIAL_BLUE_CMAP, shading="auto")
    cbar = fig.colorbar(mesh, ax=ax)
    cbar.set_label("power spectral density (dB, ref 1 g²/Hz)", color=INK_PRIMARY)
    cbar.ax.tick_params(colors=INK_MUTED, labelsize=8)

    _style_axes(ax)
    ax.set_xlabel("time since burst start (s)")
    ax.set_ylabel("frequency (Hz)")
    ax.set_title(f"pod {burst.pod_id} — axis {_AXIS_LABELS[axis_idx].upper()}")
    return fig, ax


def plot_burst_waveform(burst: VibrationBurst, ax: Axes | None = None) -> tuple[Figure, Axes]:
    """Plot all 3 axes of a vibration burst over the capture window."""
    if ax is None:
        fig, ax = plt.subplots(figsize=(9, 3.2), facecolor=CHART_SURFACE)
    else:
        fig = ax.figure

    n_samples = burst.data.shape[0]
    t = np.arange(n_samples) / burst.sample_rate_hz

    for i, label in enumerate(_AXIS_LABELS):
        ax.plot(
            t,
            burst.data[:, i],
            label=label.upper(),
            color=CATEGORICAL[i],
            linewidth=_LINEWIDTH,
        )

    _style_axes(ax)
    ax.set_xlabel("time since burst start (s)")
    ax.set_ylabel("acceleration (g)")
    ax.set_title(f"pod {burst.pod_id} burst waveform")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_SECONDARY)
    return fig, ax
