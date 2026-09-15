from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pytest

from frosty_analysis import generate_report
from frosty_analysis.report import main as report_main

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample_deployment"

EXPECTED_SECTION_MARKERS = [
    "Diagnostic Report",
    "Deployment Summary",
    "Findings",
    "Electrical",
    "Temperatures",
    "Vibration",
    "Machine State",
    "FrostSight (working name) — DRAFT",
]

SAMPLE_FINDINGS = [
    {"severity": "critical", "title": "Critical finding", "body": "critical body text"},
    {"severity": "warning", "title": "Warning finding", "body": "warning body text"},
    {"severity": "info", "title": "Info finding", "body": "info body text"},
    {"severity": "ok", "title": "OK finding", "body": "ok body text"},
]


def _count_images(html: str) -> int:
    return len(re.findall(r"<img\b", html))


# --- generate_report: sections + images ------------------------------------


def test_generate_report_writes_file(tmp_path):
    out_path = tmp_path / "report.html"
    result = generate_report(FIXTURE_DIR, out_path, findings=SAMPLE_FINDINGS)
    assert result == out_path
    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_generate_report_contains_expected_section_markers(tmp_path):
    out_path = tmp_path / "report.html"
    generate_report(FIXTURE_DIR, out_path, title="Fixture Report", findings=SAMPLE_FINDINGS)
    html = out_path.read_text(encoding="utf-8")
    for marker in EXPECTED_SECTION_MARKERS:
        assert marker in html, f"expected marker {marker!r} not found in report"
    assert "Fixture Report" in html


def test_generate_report_embeds_at_least_seven_images(tmp_path):
    # 7 guaranteed charts (current, duty cycle, 2 temp groups, condenser dT,
    # vib RMS trend, state timeline) regardless of data, plus up to one
    # spectrogram per pod if raw bursts exist (the fixture has both pods).
    out_path = tmp_path / "report.html"
    generate_report(FIXTURE_DIR, out_path, findings=SAMPLE_FINDINGS)
    html = out_path.read_text(encoding="utf-8")
    n_images = _count_images(html)
    assert n_images >= 7, f"expected at least 7 embedded images, found {n_images}"
    # base64 PNG data URIs, not external file references
    assert 'src="data:image/png;base64,' in html
    assert 'src="http' not in html


def test_generate_report_is_self_contained_html(tmp_path):
    out_path = tmp_path / "report.html"
    generate_report(FIXTURE_DIR, out_path, findings=SAMPLE_FINDINGS)
    html = out_path.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "<style>" in html  # inline CSS, no external stylesheet
    assert '<link rel="stylesheet"' not in html
    assert "page-break-inside: avoid" in html  # print-clean sectioning
    assert "size: letter" in html  # US Letter page size


def test_generate_report_header_includes_manifest_metadata(tmp_path):
    out_path = tmp_path / "report.html"
    generate_report(
        FIXTURE_DIR,
        out_path,
        prepared_for="Test Customer",
        prepared_by="Test Tech",
        findings=SAMPLE_FINDINGS,
    )
    html = out_path.read_text(encoding="utf-8")
    # from tests/fixtures/sample_deployment/manifest.json
    assert "137A" in html
    assert "SN-FIXTURE-0001" in html
    assert "Test Customer" in html
    assert "Test Tech" in html


# --- findings rendering ------------------------------------------------------


def test_findings_none_renders_neutral_placeholder(tmp_path):
    out_path = tmp_path / "report.html"
    generate_report(FIXTURE_DIR, out_path, findings=None)
    html = out_path.read_text(encoding="utf-8")
    assert "No findings supplied" in html
    assert "finding-critical" not in html


def test_findings_severity_classes_render(tmp_path):
    out_path = tmp_path / "report.html"
    generate_report(FIXTURE_DIR, out_path, findings=SAMPLE_FINDINGS)
    html = out_path.read_text(encoding="utf-8")
    for severity in ("critical", "warning", "info", "ok"):
        assert f"finding-{severity}" in html
    assert "Critical finding" in html
    assert "critical body text" in html


def test_findings_unknown_severity_falls_back_to_info(tmp_path):
    out_path = tmp_path / "report.html"
    findings = [{"severity": "weird", "title": "Mystery", "body": "body"}]
    generate_report(FIXTURE_DIR, out_path, findings=findings)
    html = out_path.read_text(encoding="utf-8")
    assert "finding-weird" in html  # class still tags the raw severity
    assert "Mystery" in html


# --- CLI ---------------------------------------------------------------------


def test_cli_main_writes_report(tmp_path):
    out_path = tmp_path / "cli_report.html"
    config_path = tmp_path / "findings.json"
    config_path.write_text(json.dumps(SAMPLE_FINDINGS), encoding="utf-8")

    exit_code = report_main(
        [str(FIXTURE_DIR), "-o", str(out_path), "--config", str(config_path)]
    )
    assert exit_code == 0
    assert out_path.exists()
    html = out_path.read_text(encoding="utf-8")
    assert "finding-critical" in html


def test_cli_subprocess_smoke(tmp_path):
    out_path = tmp_path / "subprocess_report.html"
    config = {
        "findings": SAMPLE_FINDINGS,
        "title": "Subprocess Smoke Test",
        "prepared_for": "Someone",
        "prepared_by": "Someone Else",
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "frosty_analysis.report",
            str(FIXTURE_DIR),
            "-o",
            str(out_path),
            "--config",
            str(config_path),
        ],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert out_path.exists()
    html = out_path.read_text(encoding="utf-8")
    assert "Subprocess Smoke Test" in html
    assert "Someone Else" in html
