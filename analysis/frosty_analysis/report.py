"""Self-contained HTML diagnostic report for one deployment.

Loads a deployment via `frosty_analysis.loader.load_deployment`, renders a
fully self-contained HTML file (inline CSS, matplotlib charts embedded as
base64 PNGs, no external assets) suitable for printing to US Letter or
attaching to a customer email.

Chart figures reuse `frosty_analysis.plots` wherever a plots.py function
already does the job (channel time series, the boolean state timeline, burst
spectrograms); the report-specific figures that plots.py has no equivalent
for (current envelope banding for multi-day spans, compressor cycle-duration
trend, condenser delta-T, vibration RMS trend) are built locally here using
the same dataviz-skill conventions (`CATEGORICAL`, `_style_axes`, etc.) so
the whole document reads as one visual system.

This is a print/export artifact, not an interactive dashboard, so unlike an
on-screen chart it intentionally ships a single light theme rather than a
light+dark pair — there is no viewer toggle to honor on a page meant to be
printed or emailed as a static PDF-ish document.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
from html import escape
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from frosty_analysis.loader import (
    Deployment,
    VibrationBurst,
    load_deployment,
    load_vibration_burst,
)
from frosty_analysis.plots import (
    AXIS_BASELINE,
    CATEGORICAL,
    CHART_SURFACE,
    INK_MUTED,
    INK_SECONDARY,
    _AXIS_LABELS,
    _style_axes,
    plot_burst_spectrogram,
    plot_channels,
    plot_state_timeline,
)

DPI = 150

# Status palette per the dataviz skill (fixed, never themed). Contrast on
# the light chart surface is sub-3:1 for warning/serious by design, so every
# use pairs the color with an icon + text label rather than relying on hue
# alone.
_STATUS = {
    "critical": {"color": "#d03b3b", "label": "CRITICAL", "icon": "■"},
    "warning": {"color": "#fab219", "label": "WARNING", "icon": "▲"},
    "info": {"color": "#2a78d6", "label": "INFO", "icon": "●"},
    "ok": {"color": "#0ca30c", "label": "OK", "icon": "✓"},
}
_DEFAULT_SEVERITY = "info"

_REFRIGERATION_TEMP_COLUMNS = ["temp_cylinder_c", "temp_hopper_c", "temp_discharge_c"]
_AMBIENT_TEMP_COLUMNS = ["temp_cond_in_c", "temp_cond_out_c", "temp_ambient_c"]
_CURRENT_COLUMNS = ["current_beater_a", "current_compressor_a"]
_STATE_COLUMNS = ["beater_on", "compressor_cmd", "tcc_satisfied", "hp_ok"]

_POD_LABELS = {1: "pod 1 — beater drive", 2: "pod 2 — compressor"}

EXPECTED_HZ = 1.0

__all__ = ["generate_report", "main"]


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def _fig_to_data_uri(fig: plt.Figure, dpi: int = DPI) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _img_tag(fig: plt.Figure, alt: str, dpi: int = DPI) -> str:
    uri = _fig_to_data_uri(fig, dpi=dpi)
    return f'<img class="chart-img" src="{uri}" alt="{escape(alt)}">'


def _empty_axes_note(ax: plt.Axes, text: str) -> None:
    _style_axes(ax)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.text(0.5, 0.5, text, ha="center", va="center", color=INK_MUTED, transform=ax.transAxes)


def _fmt_ts(ts) -> str:
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        return "—"
    try:
        if pd.isna(ts):
            return "—"
    except TypeError:
        pass
    return pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M UTC")


def _deployment_window(dep: Deployment) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    if len(dep.channels) == 0:
        return None, None
    return dep.channels.index.min(), dep.channels.index.max()


def _span(dep: Deployment) -> pd.Timedelta:
    start, end = _deployment_window(dep)
    if start is None:
        return pd.Timedelta(0)
    return end - start


def _resample_freq(dep: Deployment) -> str | None:
    """Pick a downsample frequency for time-series charts by deployment span.

    Short spans (the small test fixture, a few hours) render raw; longer
    spans get coarser as they grow so multi-day/multi-week decks stay
    reasonably sized.
    """
    span = _span(dep)
    if span <= pd.Timedelta(hours=6):
        return None
    if span <= pd.Timedelta(days=2):
        return "1min"
    return "5min"


def _resample_channels(channels: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Resample continuous columns by mean, boolean state columns by max.

    Max preserves "did this happen at all in this window" for booleans
    rather than washing a brief on-pulse out to a fractional mean.
    """
    if channels.empty:
        return channels
    state_cols = [c for c in _STATE_COLUMNS if c in channels.columns]
    other_cols = [c for c in channels.columns if c not in state_cols]
    parts = []
    if other_cols:
        parts.append(channels[other_cols].resample(freq).mean())
    if state_cols:
        parts.append(channels[state_cols].resample(freq).max())
    if not parts:
        return channels
    out = pd.concat(parts, axis=1)
    return out[[c for c in channels.columns if c in out.columns]]


def _view_deployment(dep: Deployment, channels: pd.DataFrame) -> Deployment:
    """A lightweight `Deployment` standing in for `dep` with different channels.

    Lets report-local code hand a resampled/derived channels frame to
    plots.py functions (which take a `Deployment`) without modifying
    plots.py or the original `dep`.
    """
    return Deployment(
        manifest=dep.manifest,
        channels=channels,
        vib_summary=dep.vib_summary,
        events=dep.events,
        burst_files=dep.burst_files,
    )


def _completeness_pct(dep: Deployment) -> float:
    start, end = _deployment_window(dep)
    if start is None:
        return 0.0
    expected = (end - start).total_seconds() * EXPECTED_HZ + 1
    if expected <= 0:
        return 0.0
    pct = 100.0 * len(dep.channels) / expected
    return max(0.0, min(100.0, pct))


# --------------------------------------------------------------------------
# report-local figures (no plots.py equivalent)
# --------------------------------------------------------------------------


def _plot_current_envelope(channels: pd.DataFrame, freq: str) -> plt.Figure:
    """Beater + compressor current as a 1-minute mean line / max envelope."""
    fig, ax = plt.subplots(figsize=(9, 3.0), facecolor=CHART_SURFACE)
    cols = [c for c in _CURRENT_COLUMNS if c in channels.columns]
    if channels.empty or not cols:
        _empty_axes_note(ax, "no current data available")
        return fig

    labels = {"current_beater_a": "beater", "current_compressor_a": "compressor"}
    mean_df = channels[cols].resample(freq).mean()
    max_df = channels[cols].resample(freq).max()
    for i, col in enumerate(cols):
        color = CATEGORICAL[i % len(CATEGORICAL)]
        ax.plot(
            mean_df.index,
            mean_df[col],
            color=color,
            linewidth=1.5,
            label=f"{labels.get(col, col)} ({freq} mean)",
        )
        ax.fill_between(
            max_df.index,
            mean_df[col],
            max_df[col],
            color=color,
            alpha=0.18,
            linewidth=0,
        )
    _style_axes(ax)
    ax.set_xlabel("time (UTC)")
    ax.set_ylabel("A")
    ax.set_title(f"Beater + compressor current — {freq} mean / max envelope")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    return fig


def _compressor_cycles(channels: pd.DataFrame) -> pd.DataFrame:
    """Derive (start, duration_s) for each complete compressor on-run."""
    if channels.empty or "compressor_cmd" not in channels.columns:
        return pd.DataFrame(columns=["start", "duration_s"])
    cmd = channels["compressor_cmd"].fillna(0).astype(int).to_numpy()
    if cmd.size == 0:
        return pd.DataFrame(columns=["start", "duration_s"])
    idx = channels.index
    rising = np.diff(cmd, prepend=0) == 1
    falling = np.diff(cmd, append=0) == -1
    start_pos = np.where(rising)[0]
    end_pos = np.where(falling)[0]
    n = min(len(start_pos), len(end_pos))
    if n == 0:
        return pd.DataFrame(columns=["start", "duration_s"])
    starts = idx[start_pos[:n]]
    ends = idx[end_pos[:n]]
    duration_s = (ends - starts).total_seconds() + 1.0  # inclusive of both boundary samples
    return pd.DataFrame({"start": starts, "duration_s": duration_s})


_SHORT_CYCLE_THRESHOLD_S = 60.0


def _plot_duty_cycle(channels: pd.DataFrame) -> plt.Figure:
    """Compressor on-cycle duration at each cycle's start time.

    A dashed reference line marks the ~60s short-cycle threshold used
    elsewhere in the diagnostic vocabulary (refrigerant-loss signature).
    """
    fig, ax = plt.subplots(figsize=(9, 2.8), facecolor=CHART_SURFACE)
    cycles = _compressor_cycles(channels)
    if cycles.empty:
        _empty_axes_note(ax, "no complete compressor on-cycles observed")
        return fig

    ax.scatter(
        cycles["start"],
        cycles["duration_s"] / 60.0,
        s=10,
        color=CATEGORICAL[0],
        alpha=0.75,
        linewidths=0,
        label="compressor on-cycle duration",
    )
    ax.axhline(
        _SHORT_CYCLE_THRESHOLD_S / 60.0,
        color=AXIS_BASELINE,
        linewidth=1.0,
        linestyle="--",
    )
    ax.text(
        cycles["start"].iloc[0],
        _SHORT_CYCLE_THRESHOLD_S / 60.0,
        " short-cycle threshold (60s)",
        color=INK_MUTED,
        fontsize=7.5,
        va="bottom",
    )
    _style_axes(ax)
    ax.set_xlabel("cycle start (UTC)")
    ax.set_ylabel("on-cycle duration (min)")
    ax.set_title("Compressor duty cycle — on-run duration over time")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    return fig


def _plot_condenser_delta_t(channels: pd.DataFrame, freq: str | None) -> plt.Figure:
    """Condenser air out - in temperature while the compressor is running."""
    fig, ax = plt.subplots(figsize=(9, 2.8), facecolor=CHART_SURFACE)
    needed = {"temp_cond_in_c", "temp_cond_out_c", "compressor_cmd"}
    if channels.empty or not needed.issubset(channels.columns):
        _empty_axes_note(ax, "condenser channels not available")
        return fig

    running = channels[channels["compressor_cmd"].fillna(0) == 1]
    if running.empty:
        _empty_axes_note(ax, "compressor never observed running")
        return fig

    delta = (running["temp_cond_out_c"] - running["temp_cond_in_c"]).dropna()
    if freq:
        delta = delta.resample(freq).mean().dropna()
    if delta.empty:
        _empty_axes_note(ax, "no condenser temperature samples while running")
        return fig

    ax.plot(
        delta.index,
        delta.values,
        color=CATEGORICAL[3],
        linewidth=1.5,
        label="condenser ΔT (out − in), compressor running",
    )
    _style_axes(ax)
    ax.set_xlabel("time (UTC)")
    ax.set_ylabel("Δ°C")
    ax.set_title("Condenser ΔT while compressor running")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    return fig


def _plot_vib_rms_trend(vib_summary: pd.DataFrame, freq: str | None) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(9, 2.9), facecolor=CHART_SURFACE)
    if vib_summary.empty or "pod_id" not in vib_summary.columns:
        _empty_axes_note(ax, "no vibration summary data")
        return fig

    pods = sorted(int(p) for p in vib_summary["pod_id"].dropna().unique())
    if not pods:
        _empty_axes_note(ax, "no vibration summary data")
        return fig

    for i, pod_id in enumerate(pods):
        sub = vib_summary[vib_summary["pod_id"] == pod_id].sort_index()
        rms_mag = np.sqrt(sub["rms_x_g"] ** 2 + sub["rms_y_g"] ** 2 + sub["rms_z_g"] ** 2)
        if freq:
            rms_mag = rms_mag.resample(freq).mean().dropna()
        color = CATEGORICAL[i % len(CATEGORICAL)]
        ax.plot(
            rms_mag.index,
            rms_mag.values,
            color=color,
            linewidth=1.5,
            label=_POD_LABELS.get(pod_id, f"pod {pod_id}"),
        )
    _style_axes(ax)
    ax.set_xlabel("time (UTC)")
    ax.set_ylabel("RMS magnitude (g)")
    ax.set_title("Vibration RMS trend by pod")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    return fig


def _representative_bursts(dep: Deployment) -> dict[int, VibrationBurst]:
    """Pick the burst with the largest peak |acceleration| per pod.

    "Representative" here means the burst most worth a technician's
    attention rather than a strictly typical/average one — the point of a
    diagnostic report is to surface the burst that looks like something,
    and this selection is purely data-driven (no special-casing of any
    particular deployment's story).
    """
    best: dict[int, VibrationBurst] = {}
    best_score: dict[int, float] = {}
    for path in dep.burst_files:
        try:
            burst = load_vibration_burst(path)
        except ValueError:
            continue
        if burst.data.size == 0:
            continue
        score = float(np.max(np.abs(burst.data)))
        if burst.pod_id not in best or score > best_score[burst.pod_id]:
            best[burst.pod_id] = burst
            best_score[burst.pod_id] = score
    return best


def _dominant_axis(burst: VibrationBurst) -> str:
    """The burst axis carrying the most AC energy (std, not raw peak).

    Z typically carries a ~1g gravity offset that would otherwise always
    win a raw-amplitude comparison regardless of which axis actually shows
    the interesting motion.
    """
    stds = np.std(burst.data, axis=0)
    return _AXIS_LABELS[int(np.argmax(stds))]


# --------------------------------------------------------------------------
# HTML section builders
# --------------------------------------------------------------------------

_CSS = """
:root {
  color-scheme: light;
  --surface-page: #f9f9f7;
  --surface-card: #fcfcfb;
  --ink-primary: #0b0b0b;
  --ink-secondary: #52514e;
  --ink-muted: #898781;
  --gridline: #e1e0d9;
  --baseline: #c3c2b7;
  --border: rgba(11, 11, 11, 0.10);
}
* { box-sizing: border-box; }
@page { size: letter; margin: 0.6in; }
body {
  margin: 0;
  padding: 24px;
  background: var(--surface-page);
  color: var(--ink-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  line-height: 1.45;
}
.report-header {
  border-bottom: 2px solid var(--ink-primary);
  padding-bottom: 12px;
  margin-bottom: 20px;
}
.report-header .kicker {
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 12px;
  color: var(--ink-muted);
}
.report-header h1 { margin: 4px 0 12px 0; font-size: 26px; }
.header-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 6px 24px;
  font-size: 13px;
  color: var(--ink-secondary);
}
.header-meta dt { font-weight: 600; color: var(--ink-primary); }
.header-meta dd { margin: 0 0 6px 0; }
.report-section {
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 18px 20px;
  margin-bottom: 20px;
  page-break-inside: avoid;
  break-inside: avoid;
}
.report-section h2 { margin-top: 0; font-size: 18px; }
.report-section h3 { font-size: 14px; margin-bottom: 4px; }
.chart-block { page-break-inside: avoid; break-inside: avoid; margin-bottom: 14px; }
.chart-img { max-width: 100%; height: auto; display: block; margin: 6px 0; border: 1px solid var(--border); border-radius: 4px; }
.stat-row { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 8px; }
.stat-tile {
  flex: 1 1 160px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
  background: var(--surface-page);
}
.stat-tile .stat-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--ink-muted); }
.stat-tile .stat-value { font-size: 20px; font-weight: 600; color: var(--ink-primary); font-variant-numeric: tabular-nums; }
.placeholder { color: var(--ink-muted); font-style: italic; }
.findings-list { list-style: none; margin: 0; padding: 0; }
.finding {
  border-left: 4px solid var(--baseline);
  background: var(--surface-page);
  border-radius: 0 6px 6px 0;
  padding: 10px 14px;
  margin-bottom: 10px;
  page-break-inside: avoid;
  break-inside: avoid;
}
.finding-badge { font-weight: 700; font-size: 11px; letter-spacing: 0.06em; }
.finding h3 { margin: 4px 0 4px 0; }
.finding p { margin: 0; color: var(--ink-secondary); }
table.events-table { width: 100%; border-collapse: collapse; font-size: 12px; }
table.events-table th, table.events-table td {
  text-align: left; padding: 4px 8px; border-bottom: 1px solid var(--gridline); vertical-align: top;
}
table.events-table th { color: var(--ink-muted); font-weight: 600; text-transform: uppercase; font-size: 10px; letter-spacing: 0.04em; }
.report-footer { margin-top: 24px; padding-top: 12px; border-top: 1px solid var(--border); font-size: 12px; color: var(--ink-muted); }
.report-footer .draft-tag { font-weight: 700; color: var(--ink-secondary); }
"""


def _section(section_id: str, title: str, body: str) -> str:
    return f'<section class="report-section" id="{escape(section_id)}"><h2>{escape(title)}</h2>{body}</section>'


def _render_header(dep: Deployment, title: str, prepared_for: str | None, prepared_by: str | None) -> str:
    manifest = dep.manifest or {}
    start, end = _deployment_window(dep)
    meta_items = [
        ("Machine model", manifest.get("machine_model", "—")),
        ("Machine serial", manifest.get("machine_serial", "—")),
        ("Deployment ID", manifest.get("deployment_id", "—")),
        ("Technician", manifest.get("technician", "—")),
        ("Firmware version", manifest.get("firmware_version", "—")),
        ("Deployment window", f"{_fmt_ts(start)} – {_fmt_ts(end)}"),
    ]
    if prepared_for:
        meta_items.append(("Prepared for", prepared_for))
    if prepared_by:
        meta_items.append(("Prepared by", prepared_by))

    meta_html = "".join(
        f"<dt>{escape(str(k))}</dt><dd>{escape(str(v))}</dd>" for k, v in meta_items
    )
    return (
        '<header class="report-header">'
        '<div class="kicker">Diagnostic Report</div>'
        f"<h1>{escape(title)}</h1>"
        f'<dl class="header-meta">{meta_html}</dl>'
        "</header>"
    )


def _render_summary(dep: Deployment) -> str:
    start, end = _deployment_window(dep)
    duration = (end - start) if start is not None else pd.Timedelta(0)
    completeness = _completeness_pct(dep)
    n_events = len(dep.events)
    n_bursts = len(dep.burst_files)
    n_vib_rows = len(dep.vib_summary)

    tiles = [
        ("Monitoring duration", f"{duration.days}d {duration.components.hours}h" if start is not None else "—"),
        ("Channel rows", f"{len(dep.channels):,}"),
        ("Data completeness", f"{completeness:.1f}%"),
        ("Vibration summary rows", f"{n_vib_rows:,}"),
        ("Raw vibration bursts", f"{n_bursts:,}"),
        ("Logged events", f"{n_events:,}"),
    ]
    tiles_html = "".join(
        f'<div class="stat-tile"><div class="stat-label">{escape(label)}</div>'
        f'<div class="stat-value">{escape(value)}</div></div>'
        for label, value in tiles
    )
    return _section("summary", "Deployment Summary", f'<div class="stat-row">{tiles_html}</div>')


def _render_findings(findings: list[dict] | None) -> str:
    if not findings:
        return _section(
            "findings",
            "Findings",
            '<p class="placeholder">No findings supplied for this report.</p>',
        )
    items = []
    for f in findings:
        severity = str(f.get("severity", _DEFAULT_SEVERITY)).lower()
        meta = _STATUS.get(severity, _STATUS[_DEFAULT_SEVERITY])
        title = escape(str(f.get("title", "")))
        body = escape(str(f.get("body", "")))
        items.append(
            f'<li class="finding finding-{escape(severity)}" style="border-left-color:{meta["color"]}">'
            f'<span class="finding-badge" style="color:{meta["color"]}">{meta["icon"]} {meta["label"]}</span>'
            f"<h3>{title}</h3><p>{body}</p></li>"
        )
    return _section("findings", "Findings", f'<ol class="findings-list">{"".join(items)}</ol>')


def _render_electrical(dep: Deployment) -> str:
    freq = _resample_freq(dep)
    if freq:
        current_fig = _plot_current_envelope(dep.channels, freq)
        current_alt = f"Beater and compressor current, {freq} mean/max envelope"
    else:
        fig, _axes = plot_channels(dep, columns=_CURRENT_COLUMNS)
        current_fig = fig
        current_alt = "Beater and compressor current over time"

    duty_fig = _plot_duty_cycle(dep.channels)

    body = (
        '<div class="chart-block">'
        f"{_img_tag(current_fig, current_alt)}"
        "</div>"
        '<div class="chart-block">'
        f'{_img_tag(duty_fig, "Compressor duty cycle: on-run duration over time")}'
        "</div>"
    )
    return _section("electrical", "Electrical", body)


def _render_temperatures(dep: Deployment) -> str:
    freq = _resample_freq(dep)
    if freq:
        view = _view_deployment(dep, _resample_channels(dep.channels, freq))
    else:
        view = dep

    refrig_cols = [c for c in _REFRIGERATION_TEMP_COLUMNS if c in dep.channels.columns]
    ambient_cols = [c for c in _AMBIENT_TEMP_COLUMNS if c in dep.channels.columns]

    blocks = []
    if refrig_cols:
        fig, _axes = plot_channels(view, columns=refrig_cols)
        blocks.append(_img_tag(fig, "Refrigeration-side temperatures over time"))
    if ambient_cols:
        fig, _axes = plot_channels(view, columns=ambient_cols)
        blocks.append(_img_tag(fig, "Ambient / condenser temperatures over time"))

    delta_t_fig = _plot_condenser_delta_t(dep.channels, freq)
    blocks.append(_img_tag(delta_t_fig, "Condenser delta-T while compressor running"))

    body = "".join(f'<div class="chart-block">{b}</div>' for b in blocks)
    return _section("temperatures", "Temperatures", body)


def _render_vibration(dep: Deployment) -> str:
    freq = _resample_freq(dep)
    rms_fig = _plot_vib_rms_trend(dep.vib_summary, freq)
    blocks = [_img_tag(rms_fig, "Vibration RMS trend by pod")]

    for pod_id, burst in sorted(_representative_bursts(dep).items()):
        spec_fig, _ax = plot_burst_spectrogram(burst, axis=_dominant_axis(burst))
        blocks.append(
            _img_tag(
                spec_fig,
                f"Representative vibration burst spectrogram, {_POD_LABELS.get(pod_id, f'pod {pod_id}')}",
            )
        )

    body = "".join(f'<div class="chart-block">{b}</div>' for b in blocks)
    return _section("vibration", "Vibration", body)


def _render_state_and_events(dep: Deployment) -> str:
    freq = _resample_freq(dep)
    if freq:
        view = _view_deployment(dep, _resample_channels(dep.channels, freq))
    else:
        view = dep
    fig, _ax = plot_state_timeline(view)
    state_block = f'<div class="chart-block">{_img_tag(fig, "Machine state timeline")}</div>'

    if dep.events.empty:
        events_block = '<p class="placeholder">No journal-button or system events logged.</p>'
    else:
        rows = []
        for ts, row in dep.events.iterrows():
            detail = row.get("detail", {})
            try:
                detail_str = json.dumps(detail, separators=(",", ": "), default=str)
            except TypeError:
                detail_str = str(detail)
            rows.append(
                "<tr>"
                f"<td>{escape(_fmt_ts(ts))}</td>"
                f'<td>{escape(str(row.get("type", "")))}</td>'
                f"<td>{escape(detail_str)}</td>"
                "</tr>"
            )
        events_block = (
            '<table class="events-table">'
            "<thead><tr><th>Timestamp</th><th>Type</th><th>Detail</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
        )

    body = state_block + f'<h3>Journal &amp; system events</h3>{events_block}'
    return _section("state-events", "Machine State &amp; Events", body)


def _render_footer(dep: Deployment) -> str:
    manifest = dep.manifest or {}
    fw = manifest.get("firmware_version", "unknown")
    generated_at = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")
    return (
        '<footer class="report-footer">'
        f"<div>Firmware version: {escape(str(fw))} &middot; Report generated {escape(generated_at)}</div>"
        '<div class="draft-tag">FrostSight (working name) — DRAFT</div>'
        "</footer>"
    )


def _render_report_html(
    dep: Deployment,
    *,
    title: str,
    findings: list[dict] | None,
    prepared_for: str | None,
    prepared_by: str | None,
) -> str:
    sections = [
        _render_summary(dep),
        _render_findings(findings),
        _render_electrical(dep),
        _render_temperatures(dep),
        _render_vibration(dep),
        _render_state_and_events(dep),
    ]
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>{escape(title)}</title>"
        f"<style>{_CSS}</style>"
        "</head><body>"
        f"{_render_header(dep, title, prepared_for, prepared_by)}"
        f"{''.join(sections)}"
        f"{_render_footer(dep)}"
        "</body></html>"
    )


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------


def generate_report(
    deployment_path: str | Path,
    output_path: str | Path,
    *,
    title: str | None = None,
    findings: list[dict] | None = None,
    prepared_for: str | None = None,
    prepared_by: str | None = None,
) -> Path:
    """Render a self-contained HTML diagnostic report for one deployment.

    `deployment_path` is a directory laid out per
    `docs/firmware/data-format-spec.md` (as read by `load_deployment`).
    `findings` is an ordered list of `{severity, title, body}` dicts,
    `severity` one of `"critical" | "warning" | "info" | "ok"`; pass `None`
    to render a neutral placeholder instead.

    Returns the output path.
    """
    dep = load_deployment(deployment_path)
    resolved_title = title or (dep.manifest or {}).get("deployment_id") or "Diagnostic Report"
    html = _render_report_html(
        dep,
        title=resolved_title,
        findings=findings,
        prepared_for=prepared_for,
        prepared_by=prepared_by,
    )
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m frosty_analysis.report",
        description="Render a self-contained HTML diagnostic report from a frosty-monitor deployment directory.",
    )
    parser.add_argument("deployment_dir", type=Path, help="Path to a deployment directory (manifest.json + channels_*.csv etc.)")
    parser.add_argument("-o", "--output", type=Path, default=Path("report.html"), help="Output HTML path (default: report.html)")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional JSON file: either a list of finding dicts, or an object with any of "
        "'findings', 'title', 'prepared_for', 'prepared_by' keys.",
    )
    args = parser.parse_args(argv)

    title = None
    findings = None
    prepared_for = None
    prepared_by = None
    if args.config is not None:
        with open(args.config, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        if isinstance(cfg, list):
            findings = cfg
        elif isinstance(cfg, dict):
            findings = cfg.get("findings")
            title = cfg.get("title")
            prepared_for = cfg.get("prepared_for")
            prepared_by = cfg.get("prepared_by")
        else:
            raise ValueError(f"{args.config}: expected a JSON list or object")

    out = generate_report(
        args.deployment_dir,
        args.output,
        title=title,
        findings=findings,
        prepared_for=prepared_for,
        prepared_by=prepared_by,
    )
    print(f"Wrote report to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
