"""Build proposal/failure-signatures.html.

Scratch build script -- not part of the analysis package. Generates one
matplotlib chart per failure mode from frosty_analysis.synthetic, embeds
them as base64 PNGs, and writes the self-contained gallery HTML.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from frosty_analysis import signatures as sig
from frosty_analysis import synthetic as syn
from frosty_analysis.plots import (
    AXIS_BASELINE,
    CATEGORICAL,
    CHART_SURFACE,
    GRIDLINE,
    INK_MUTED,
    INK_PRIMARY,
    INK_SECONDARY,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "proposal" / "failure-signatures.html"

HEALTHY_COLOR = CATEGORICAL[0]  # blue -- fixed identity across every chart
FAIL_COLOR = CATEGORICAL[7]  # red -- fixed identity across every chart
LINEWIDTH = 1.8


def style_axes(ax):
    ax.set_facecolor(CHART_SURFACE)
    ax.grid(True, color=GRIDLINE, linewidth=0.8, alpha=0.9)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(AXIS_BASELINE)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    ax.xaxis.label.set_color(INK_PRIMARY)
    ax.yaxis.label.set_color(INK_PRIMARY)
    ax.title.set_color(INK_PRIMARY)


def legend_above(ax, ncol=2):
    """Place the legend as a row above the axes (never inside the plot),
    so it never collides with an in-plot annotation box."""
    ax.legend(
        loc="lower left",
        bbox_to_anchor=(0.0, 1.02, 1.0, 0.12),
        mode="expand",
        ncol=ncol,
        frameon=False,
        fontsize=9,
        labelcolor=INK_SECONDARY,
        handlelength=1.8,
        columnspacing=1.4,
        borderaxespad=0,
    )


def fig_to_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor=CHART_SURFACE, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def minutes_elapsed(index: pd.DatetimeIndex) -> np.ndarray:
    return (index - index[0]).total_seconds() / 60.0


def hours_elapsed(index: pd.DatetimeIndex) -> np.ndarray:
    return (index - index[0]).total_seconds() / 3600.0


# --- 1. short cycling --------------------------------------------------


def chart_short_cycling() -> str:
    healthy = syn.make_healthy(hours=1.0, rng=1001)
    failing = syn.make_short_cycling(hours=1.0, rng=1002)

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(7.6, 4.6), sharex=True, facecolor=CHART_SURFACE
    )

    t1 = minutes_elapsed(healthy.channels.index)
    ax1.plot(t1, healthy.channels["current_compressor_a"], color=HEALTHY_COLOR, linewidth=LINEWIDTH)
    ax1.set_title("Normal operation", loc="left", fontsize=10, fontweight="bold")
    style_axes(ax1)
    ax1.set_ylabel("compressor draw (A)")

    t2 = minutes_elapsed(failing.channels.index)
    ax2.plot(t2, failing.channels["current_compressor_a"], color=FAIL_COLOR, linewidth=LINEWIDTH)
    ax2.set_title("Short-cycling", loc="left", fontsize=10, fontweight="bold")
    style_axes(ax2)
    ax2.set_ylabel("compressor draw (A)")
    ax2.set_xlabel("minutes elapsed")

    ax2.annotate(
        "On, then off again in under a minute\n-- over and over",
        xy=(t2[300] if len(t2) > 300 else t2[len(t2) // 4], 7.0),
        xytext=(24, 3.0),
        fontsize=8.5,
        color=INK_PRIMARY,
        arrowprops=dict(arrowstyle="->", color=INK_SECONDARY, linewidth=1.2),
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor=AXIS_BASELINE),
    )
    fig.tight_layout()
    return fig_to_base64(fig)


# --- 2. TCC never satisfied ---------------------------------------------


def chart_tcc_never_satisfied() -> str:
    healthy = syn.make_healthy(hours=3.0, rng=1101)
    failing = syn.make_tcc_never_satisfied(hours=3.0, rng=1102)

    fig, ax = plt.subplots(figsize=(7.6, 3.6), facecolor=CHART_SURFACE)
    th = hours_elapsed(healthy.channels.index)
    tf = hours_elapsed(failing.channels.index)
    ax.plot(
        th, healthy.channels["current_beater_a"], color=HEALTHY_COLOR,
        linewidth=LINEWIDTH, label="Healthy — cycles on and off",
    )
    ax.plot(
        tf, failing.channels["current_beater_a"], color=FAIL_COLOR,
        linewidth=LINEWIDTH, label="Never satisfies — runs the whole time",
    )
    style_axes(ax)
    ax.set_xlabel("hours elapsed")
    ax.set_ylabel("beater motor draw (A)")
    legend_above(ax)

    ax.annotate(
        "Straight line for hours --\nnever reaches a stopping point",
        xy=(2.2, float(failing.channels["current_beater_a"].iloc[int(2.2 * 3600)])),
        xytext=(0.9, 5.6),
        fontsize=8.5,
        color=INK_PRIMARY,
        arrowprops=dict(arrowstyle="->", color=INK_SECONDARY, linewidth=1.2),
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor=AXIS_BASELINE),
    )
    return fig_to_base64(fig)


# --- 3. condenser airflow -----------------------------------------------


def chart_condenser_airflow() -> str:
    healthy = syn.make_healthy(hours=10.0, rng=1201)
    failing = syn.make_condenser_airflow(hours=10.0, rng=1202)

    def delta_series(channels):
        delta = channels["temp_cond_out_c"] - channels["temp_cond_in_c"]
        smoothed = delta.rolling("5min").mean()
        return smoothed.iloc[::60]

    dh = delta_series(healthy.channels)
    df_ = delta_series(failing.channels)

    fig, ax = plt.subplots(figsize=(7.6, 3.6), facecolor=CHART_SURFACE)
    ax.plot(
        hours_elapsed(dh.index), dh, color=HEALTHY_COLOR, linewidth=LINEWIDTH,
        label="Healthy condenser",
    )
    ax.plot(
        hours_elapsed(df_.index), df_, color=FAIL_COLOR, linewidth=LINEWIDTH,
        label="Clogged condenser",
    )
    style_axes(ax)
    ax.set_xlabel("hours elapsed")
    ax.set_ylabel("condenser air temperature rise (°C)\n(bigger = better airflow)")
    legend_above(ax)

    end_h = hours_elapsed(df_.index)[-1]
    end_v = float(df_.iloc[-1])
    ax.annotate(
        "Barely any temperature\nrise left by hour 10",
        xy=(end_h - 0.3, end_v),
        xytext=(end_h - 4.2, end_v + 4.5),
        fontsize=8.5,
        color=INK_PRIMARY,
        arrowprops=dict(arrowstyle="->", color=INK_SECONDARY, linewidth=1.2),
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor=AXIS_BASELINE),
    )
    return fig_to_base64(fig)


# --- 4. knocking ----------------------------------------------------------


def chart_knocking() -> str:
    healthy = syn.make_healthy(hours=2.5, rng=1301)
    failing = syn.make_knocking(hours=2.5, rng=1302)

    def beater_rms(vib):
        pod1 = vib[vib["pod_id"] == 1].sort_index()
        return pod1[["rms_x_g", "rms_y_g", "rms_z_g"]].mean(axis=1)

    rh = beater_rms(healthy.vib_summary)
    rf = beater_rms(failing.vib_summary)

    fig, ax = plt.subplots(figsize=(7.6, 3.6), facecolor=CHART_SURFACE)
    ax.plot(
        hours_elapsed(rh.index), rh, color=HEALTHY_COLOR, linewidth=LINEWIDTH,
        label="Healthy",
    )
    ax.plot(
        hours_elapsed(rf.index), rf, color=FAIL_COLOR, linewidth=LINEWIDTH,
        label="Knocking",
    )
    style_axes(ax)
    ax.set_xlabel("hours elapsed")
    ax.set_ylabel("shaking at the beater drive (g)\n(higher = more shaking)")
    legend_above(ax)

    spike_idx = int(np.argmax(rf.to_numpy()))
    spike_h = hours_elapsed(rf.index)[spike_idx]
    spike_v = float(rf.iloc[spike_idx])
    ax.annotate(
        "Sharp jolt --\nrepeats every freeze-down",
        xy=(spike_h, spike_v),
        xytext=(spike_h + 0.35, spike_v * 0.95),
        fontsize=8.5,
        color=INK_PRIMARY,
        arrowprops=dict(arrowstyle="->", color=INK_SECONDARY, linewidth=1.2),
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor=AXIS_BASELINE),
    )
    return fig_to_base64(fig)


# --- 5. belt slip ---------------------------------------------------------


def chart_belt_slip() -> str:
    healthy = syn.make_healthy(hours=1.5, rng=1401)
    failing = syn.make_belt_slip(hours=1.5, rng=1402)

    fig, ax = plt.subplots(figsize=(7.6, 3.6), facecolor=CHART_SURFACE)
    th = minutes_elapsed(healthy.channels.index)
    tf = minutes_elapsed(failing.channels.index)
    ax.plot(
        th, healthy.channels["current_beater_a"], color=HEALTHY_COLOR,
        linewidth=LINEWIDTH, label="Healthy — motor under load",
    )
    ax.plot(
        tf, failing.channels["current_beater_a"], color=FAIL_COLOR,
        linewidth=LINEWIDTH, label="Belt slipping — motor spinning free",
    )
    style_axes(ax)
    ax.set_xlabel("minutes elapsed")
    ax.set_ylabel("beater motor draw (A)")
    legend_above(ax)

    idx = len(tf) // 3
    ax.annotate(
        "Motor's on, but barely\ndrawing any power --\nnothing engaged",
        xy=(tf[idx], float(failing.channels["current_beater_a"].iloc[idx])),
        xytext=(tf[idx] + 14, 2.15),
        fontsize=8.5,
        color=INK_PRIMARY,
        arrowprops=dict(arrowstyle="->", color=INK_SECONDARY, linewidth=1.2),
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor=AXIS_BASELINE),
    )
    return fig_to_base64(fig)


# --- 6. motor degradation ---------------------------------------------------


def chart_motor_degradation() -> str:
    healthy = syn.make_healthy(hours=504.0, rng=1501)  # 21 days at 1Hz
    failing = syn.make_motor_degradation(days=21, rng=1502)

    def daily_median(channels):
        loaded = channels.loc[channels["beater_on"] == 1, "current_beater_a"].dropna()
        return loaded.groupby(loaded.index.normalize()).median()

    dh = daily_median(healthy.channels)
    df_ = daily_median(failing.channels)

    fig, ax = plt.subplots(figsize=(7.6, 3.6), facecolor=CHART_SURFACE)
    ax.plot(
        range(len(dh)), dh.to_numpy(), color=HEALTHY_COLOR, linewidth=LINEWIDTH,
        marker="o", markersize=4.5, label="Healthy machine",
    )
    ax.plot(
        range(len(df_)), df_.to_numpy(), color=FAIL_COLOR, linewidth=LINEWIDTH,
        marker="o", markersize=4.5, label="Wearing motor",
    )
    style_axes(ax)
    ax.set_xlabel("day of deployment")
    ax.set_ylabel("typical beater motor draw\nunder load, per day (A)")
    legend_above(ax)

    last = len(df_) - 1
    ax.annotate(
        f"Up {df_.iloc[-1] - df_.iloc[0]:.1f}A over 3 weeks --\nsteady climb, day after day",
        xy=(last, float(df_.iloc[-1])),
        xytext=(last - 9, float(df_.iloc[-1]) + 0.35),
        fontsize=8.5,
        color=INK_PRIMARY,
        arrowprops=dict(arrowstyle="->", color=INK_SECONDARY, linewidth=1.2),
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor=AXIS_BASELINE),
    )
    return fig_to_base64(fig)


# --- 7. seal failure (leak) -------------------------------------------------


def chart_seal_failure() -> str:
    healthy = syn.make_healthy(hours=504.0, rng=1601)  # 21 days at 1Hz
    failing = syn.make_seal_failure(days=21, rng=1602)

    def daily_max_drip(channels):
        s = channels["drip_rate_cpm"].dropna()
        return s.groupby(s.index.normalize()).max()

    dh = daily_max_drip(healthy.channels)
    df_ = daily_max_drip(failing.channels)

    fig, ax = plt.subplots(figsize=(7.6, 3.6), facecolor=CHART_SURFACE)
    ax.plot(
        range(len(dh)), dh.to_numpy(), color=HEALTHY_COLOR, linewidth=LINEWIDTH,
        marker="o", markersize=4.5, label="Healthy — occasional isolated drops",
    )
    ax.plot(
        range(len(df_)), df_.to_numpy(), color=FAIL_COLOR, linewidth=LINEWIDTH,
        marker="o", markersize=4.5, label="Worn rear seal — steady climb",
    )
    style_axes(ax)
    ax.set_xlabel("day of deployment")
    ax.set_ylabel("drip rate at the drip tube,\nbusiest reading per day (drops/min)")
    legend_above(ax)

    healthy_pick = min(len(dh) - 2, len(dh) - 1)
    ax.annotate(
        "A drop here, a drop there --\nnever adds up to a trend",
        xy=(healthy_pick, float(dh.iloc[healthy_pick])),
        xytext=(max(healthy_pick - 9, 0), float(dh.max()) + 3.0),
        fontsize=8.5,
        color=INK_PRIMARY,
        arrowprops=dict(arrowstyle="->", color=INK_SECONDARY, linewidth=1.2),
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor=AXIS_BASELINE),
    )
    last = len(df_) - 1
    ax.annotate(
        f"Up to {df_.iloc[-1]:.0f} drops/min and\nstill climbing -- not a one-off",
        xy=(last, float(df_.iloc[-1])),
        xytext=(last - 10, float(df_.iloc[-1]) - 4.5),
        fontsize=8.5,
        color=INK_PRIMARY,
        arrowprops=dict(arrowstyle="->", color=INK_SECONDARY, linewidth=1.2),
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor=AXIS_BASELINE),
    )
    return fig_to_base64(fig)


# --- assemble HTML -----------------------------------------------------

SECTIONS = [
    {
        "id": "short-cycling",
        "name": "Compressor short-cycling",
        "subtitle": "Often the first sign of a refrigerant leak",
        "experience": (
            "The machine sounds like it's constantly kicking the compressor on and off, "
            "sometimes several times a minute. Drinks and shakes come out warmer and "
            "softer than usual, because the compressor never gets a long-enough run to "
            "do its job before it cuts out again."
        ),
        "chart_fn": chart_short_cycling,
        "recommend": "Call a refrigeration tech to check the refrigerant charge for a leak.",
    },
    {
        "id": "tcc-never-satisfied",
        "name": "Machine never reaches consistency",
        "subtitle": "It runs and runs, but never calls itself “done”",
        "experience": (
            "The compressor and beater motor just keep running, sometimes for hours, "
            "and the product never firms up to a proper serving consistency. The "
            "machine is working as hard as it can without ever reaching the point "
            "where it's supposed to back off."
        ),
        "chart_fn": chart_tcc_never_satisfied,
        "recommend": "Check the mix ratio and the machine's cutoff switch — it may need "
        "adjustment or replacement.",
    },
    {
        "id": "condenser-airflow",
        "name": "Clogged condenser / blocked airflow",
        "subtitle": "The machine can't get rid of the heat it pulls out of the mix",
        "experience": (
            "The machine runs hotter than it used to, and the space around it may feel "
            "warmer too. Over time it takes longer to make product, and eventually it "
            "may start behaving like it's low on refrigerant even though nothing has "
            "leaked -- the condenser (the coil that dumps heat outside the machine) is "
            "just blocked with dust or lint and can't move air through it anymore."
        ),
        "chart_fn": chart_condenser_airflow,
        "recommend": "Clean the condenser coil and check that vents/airflow around the "
        "machine aren't blocked.",
    },
    {
        "id": "knocking",
        "name": "Knocking during freeze-down",
        "subtitle": "A sharp, repeated jolt or bang while the machine is freezing product",
        "experience": (
            "You hear (and can sometimes feel) a distinct knock or bang, usually early "
            "in a freeze cycle, repeating every so often rather than being one-off "
            "noise. It's usually a hard chunk of ice or a slug of air hitting the "
            "inside of the freezing cylinder, or a scraper blade that's come loose."
        ),
        "chart_fn": chart_knocking,
        "recommend": "Have a tech inspect the scraper blades and check for air/ice "
        "buildup in the cylinder.",
    },
    {
        "id": "belt-slip",
        "name": "Slipping or broken drive belt",
        "subtitle": "The motor spins, but nothing happens",
        "experience": (
            "The beater motor sounds like it's running, but the product doesn't mix "
            "or freeze properly -- it stays liquid, or freezes unevenly. The motor "
            "itself isn't straining at all, because the belt that's supposed to "
            "connect it to the dasher inside the cylinder is slipping or has broken."
        ),
        "chart_fn": chart_belt_slip,
        "recommend": "Inspect and replace the drive belt.",
    },
    {
        "id": "motor-degradation",
        "name": "Drive motor wearing out",
        "subtitle": "A slow, steady climb over weeks, not a sudden failure",
        "experience": (
            "Nothing dramatic happens day to day, but the beater motor is quietly "
            "drawing more and more power to do the same job, week over week, as "
            "bearings or windings wear down inside it. Left alone, this typically "
            "ends in a sudden motor failure with no warning on the day it happens."
        ),
        "chart_fn": chart_motor_degradation,
        "recommend": "Plan a motor replacement at the next scheduled service, before it "
        "fails unexpectedly -- a planned swap is far cheaper than an emergency one.",
    },
    {
        "id": "seal-failure",
        "name": "Leaking rear seal — the drip that tells you before the puddle does",
        "subtitle": "A slow drip from the drip tube, building over weeks into something you can't ignore",
        "experience": (
            "You'd notice drips from the tube under the faceplate, a bit of mix or "
            "refrigerant residue on the floor under the machine, and eventually product "
            "loss as the rear cylinder seal wears through. It rarely starts as a puddle "
            "-- it starts as an occasional drop that's easy to wipe up and forget about, "
            "and only becomes obvious once it's already a steady leak."
        ),
        "chart_fn": chart_seal_failure,
        "recommend": "Schedule an inexpensive seal kit replacement at the machine's next "
        "scheduled service. This is a wear item and is not covered by the machine's "
        "warranty -- which is exactly why catching it early, before it turns into a "
        "bigger repair, matters.",
    },
]


def build_section_html(section: dict) -> str:
    img_b64 = section["chart_fn"]()
    return f"""
    <section class="signature">
      <h2>{section['name']}</h2>
      <p class="subtitle">{section['subtitle']}</p>
      <p class="experience">{section['experience']}</p>
      <figure>
        <img src="data:image/png;base64,{img_b64}" alt="{section['name']} — healthy vs. failing chart" />
      </figure>
      <p class="recommend"><strong>What we'd recommend:</strong> {section['recommend']}</p>
    </section>
    """


def build_html() -> str:
    sections_html = "\n".join(build_section_html(s) for s in SECTIONS)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>FrostSight — Failure Signature Gallery</title>
<style>
  :root {{
    --accent: {CATEGORICAL[0]};
    --accent-dark: #184f95;
    --ink: {INK_PRIMARY};
    --ink-secondary: {INK_SECONDARY};
    --ink-muted: {INK_MUTED};
    --border: {GRIDLINE};
    --surface: {CHART_SURFACE};
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: var(--ink);
    line-height: 1.5;
    font-size: 14px;
    max-width: 840px;
    margin: 0 auto;
    padding: 1.4rem 1.6rem 2.2rem;
    background: #ffffff;
  }}
  header.doc-header {{
    border-bottom: 3px solid var(--accent-dark);
    padding-bottom: 0.7rem;
    margin-bottom: 0.5rem;
  }}
  header.doc-header h1 {{
    color: var(--accent-dark);
    margin: 0 0 0.3rem;
    font-size: 1.55rem;
    letter-spacing: -0.01em;
  }}
  header.doc-header .subtitle {{
    color: var(--ink-secondary);
    font-size: 0.92rem;
    margin: 0;
  }}
  header.doc-header .disclaimer {{
    color: var(--ink-muted);
    font-size: 0.8rem;
    margin: 0.35rem 0 0;
    font-style: italic;
  }}
  section.signature {{
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem 1.2rem 1.1rem;
    margin: 1.1rem 0;
    page-break-inside: avoid;
    break-inside: avoid;
  }}
  section.signature h2 {{
    color: var(--accent-dark);
    margin: 0 0 0.15rem;
    font-size: 1.15rem;
  }}
  section.signature p.subtitle {{
    color: var(--ink-secondary);
    font-size: 0.92rem;
    font-style: italic;
    margin: 0 0 0.55rem;
  }}
  section.signature p.experience {{
    margin: 0 0 0.7rem;
    font-size: 0.94rem;
  }}
  figure {{
    margin: 0 0 0.7rem;
    text-align: center;
  }}
  figure img {{
    max-width: 100%;
    height: auto;
    border: 1px solid var(--border);
    border-radius: 4px;
  }}
  p.recommend {{
    background: #f3f6fa;
    border-left: 4px solid var(--accent);
    padding: 0.5rem 0.75rem;
    margin: 0;
    font-size: 0.92rem;
  }}
  footer {{
    margin-top: 1.6rem;
    padding-top: 0.8rem;
    border-top: 1px solid var(--border);
    color: var(--ink-muted);
    font-size: 0.8rem;
    text-align: center;
  }}
  @page {{
    size: Letter;
    margin: 0.6in;
  }}
  @media print {{
    body {{ max-width: 100%; padding: 0; }}
    section.signature {{ page-break-inside: avoid; }}
  }}
</style>
</head>
<body>
  <header class="doc-header">
    <h1>What failure looks like in the data — FrostSight signature gallery</h1>
    <p class="subtitle">
      Seven ways a Frosty Factory machine tells you something's wrong, if you know
      where to look. Each chart below compares a healthy machine against a
      documented failure mode over the same kind of stretch of time.
    </p>
    <p class="disclaimer">
      The charts on this page are synthetic, illustrative data generated to show
      the shape of each failure mode clearly — not recordings from a real
      customer machine.
    </p>
  </header>

  {sections_html}

  <footer>
    FrostSight (working name) — Ben Tomasik — illustrative synthetic data, not customer data.
  </footer>
</body>
</html>
"""


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    html = build_html()
    OUT_PATH.write_text(html, encoding="utf-8")
    size_kb = len(html.encode("utf-8")) / 1024
    print(f"wrote {OUT_PATH} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
