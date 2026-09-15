"""Regenerate proposal/sample-diagnostic-report.html from the synthetic demo deployment.

Usage:
    python make_demo_deployment.py --out-dir /path/to/demo_deployment   # first, ~113MB
    python make_sample_report.py /path/to/demo_deployment

The demo dataset is deliberately not committed; only this script and the
rendered HTML are. The findings below narrate the failure story that
make_demo_deployment.py injects (short-cycling from day 6, day-9 knock with a
correlated staff button press, slow condenser air-in drift).
"""

import argparse
import pathlib

from frosty_analysis import generate_report

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "proposal" / "sample-diagnostic-report.html"

FINDINGS = [
    {
        "severity": "critical",
        "title": "Compressor short-cycling — pattern consistent with refrigerant loss",
        "body": (
            "Starting around day 6 of the deployment, compressor on-cycle durations begin shortening "
            "specifically during the warm afternoon hours (13:00-18:00), and by the final days of the "
            "window roughly half of afternoon cycles run under 60 seconds — well short of this "
            "machine's healthy 4-8 minute freeze-down cycle. Condenser delta-T during those short "
            "cycles falls to about two-thirds of the ~12°C healthy baseline, a roughly 30-40% "
            "reduction in heat rejection. Together, short run times with reduced condenser delta-T "
            "during the hottest part of the day is the classic short-cycling signature of a slow "
            "refrigerant leak: as charge drops, the system satisfies (or trips) faster and faster "
            "without properly cooling the cylinder. Recommend a refrigeration technician perform a "
            "leak check and recharge as needed. If a leak is confirmed and repair cost approaches or "
            "exceeds roughly 50% of the cost of a new unit (“the 50% rule”), replacement is "
            "usually the more cost-effective call, especially on an older compressor system."
        ),
    },
    {
        "severity": "warning",
        "title": "Knocking episode on day 9 correlated with staff report",
        "body": (
            "At 21:15 UTC on day 9, the beater-drive vibration pod (pod 1) recorded a sharp RMS spike "
            "with strong low-frequency (5-50Hz band) energy, well above its normal running level, and "
            "the firmware's automatic trigger captured a raw burst at that moment. A staff member "
            "logged a journal-button entry 2.5 minutes later reporting a knocking/rattling noise from "
            "the freezing cylinder — the auto-capture and the staff report line up almost exactly. "
            "This combination (low-frequency impact energy on the beater pod plus an audible knock) is "
            "the classic signature of ice buildup or a too-lean mix (sugar/solids) ratio causing the "
            "beater to strike ice chunks inside the cylinder. Recommend checking the mix ratio against "
            "spec and inspecting the cylinder for ice buildup at next service."
        ),
    },
    {
        "severity": "info",
        "title": "Condenser airflow trending down",
        "body": (
            "Condenser air-intake temperature drifted upward roughly 2°C over the 14-day window "
            "(daily mean ~23.0°C on day 1 to ~25.1°C on day 14), a slow, steady trend "
            "independent of the day-to-day diurnal swing. This pattern is consistent with gradually "
            "reduced airflow — dust or lint buildup on the condenser coil, a slowing condenser fan, or "
            "a partially obstructed intake — rather than a step change. Recommend a condenser coil "
            "cleaning and fan check at the next scheduled service visit before it compounds the "
            "refrigerant-side finding above."
        ),
    },
    {
        "severity": "ok",
        "title": "Beater drive healthy",
        "body": (
            "Beater motor current draw stayed within a stable, consistent range across the full "
            "deployment with no long-term upward drift, and beater-pod (pod 1) vibration shows no "
            "abnormal trend outside the isolated day-9 knocking episode noted above. No action needed "
            "on the beater drive itself."
        ),
    },
]

SAMPLE_CSS = """
<style>
.sample-banner {
  background: #fab219; color: #0b0b0b; font-weight: 700; font-size: 13px;
  letter-spacing: 0.03em; text-align: center; padding: 8px 12px;
  border-radius: 6px; margin-bottom: 16px;
}
.sample-watermark {
  position: fixed; top: 50%; left: 50%;
  transform: translate(-50%, -50%) rotate(-30deg);
  font-size: 54px; font-weight: 800; color: rgba(208, 59, 59, 0.16);
  letter-spacing: 3px; white-space: nowrap; pointer-events: none; z-index: 9999;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
}
@media print { .sample-watermark { position: fixed; } }
</style>
"""

SAMPLE_BANNER = (
    '<div class="sample-watermark">SAMPLE REPORT — SYNTHETIC DATA</div>'
    '<div class="sample-banner">▲ SAMPLE REPORT — SYNTHETIC DATA FOR DEMONSTRATION. '
    "All machine data in this document is computer-generated for a fictitious customer and does not "
    "represent an actual diagnostic engagement.</div>"
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("demo_dir", type=pathlib.Path, help="demo deployment directory")
    ap.add_argument("-o", "--output", type=pathlib.Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    generate_report(
        args.demo_dir,
        args.output,
        title="137A Diagnostic Report — Neighborhood Cantina (SAMPLE)",
        findings=FINDINGS,
        prepared_for="Sample Customer — Neighborhood Cantina (fictitious)",
        prepared_by="Ben Tomasik, FrostSight",
    )

    html = args.output.read_text(encoding="utf-8")
    assert "</head><body>" in html, "expected </head><body> marker not found"
    html = html.replace("</head><body>", f"</head>{SAMPLE_CSS}<body>{SAMPLE_BANNER}", 1)
    html = html.replace(
        "<title>137A Diagnostic Report", "<title>[SAMPLE] 137A Diagnostic Report", 1
    )
    args.output.write_text(html, encoding="utf-8")

    size_mb = args.output.stat().st_size / (1024 * 1024)
    print(f"wrote {args.output} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
