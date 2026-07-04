"""Tests for the scan-job runner (mocked scanner, no hardware)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import numpy as np

from santecpro.job_runner import run_job
from santecpro.jobscript import parse_job
from santecpro.results import ScanResult


def _fake_result(channels=(1,), n=3):
    ch = {c: np.array([-10.0 - c, -11.0 - c, -12.0 - c][:n]) for c in channels}
    return ScanResult(
        wavelengths=np.array([1500.0, 1500.5, 1501.0][:n]),
        powers=ch[channels[0]],
        monitor_powers=np.array([7.0, 7.1, 7.2][:n]),
        channel_powers=ch,
    )


def _scanner():
    m = MagicMock()
    m.run_stsprocess_scan.return_value = _fake_result()
    return m


def test_runs_each_segment_and_writes_files(tmp_path):
    job = parse_job(
        "job jobA\n"
        "scan a 1500 1501 step=1pm speed=10\n"
        "scan b 1500 1501 step=1pm speed=10 dir=reverse\n"
    )
    scanner = _scanner()
    results = run_job(job, scanner, tmp_path, timestamp="20260704_120000")

    assert scanner.run_stsprocess_scan.call_count == 2
    first = scanner.run_stsprocess_scan.call_args_list[0].kwargs
    assert first["start_wl"] == 1500.0 and first["stop_wl"] == 1501.0
    assert first["plot"] is False
    second = scanner.run_stsprocess_scan.call_args_list[1].kwargs
    assert second["start_wl"] == 1501.0 and second["stop_wl"] == 1500.0  # reverse swapped

    job_dir = tmp_path / "jobA_20260704_120000"
    assert (job_dir / "01_a_fwd.csv").exists()
    assert (job_dir / "02_b_rev.csv").exists()
    assert (job_dir / "manifest.json").exists()
    assert all(r.ok for r in results)
    assert results[0].points == 3


def test_csv_has_header_and_rows(tmp_path):
    job = parse_job("scan a 1500 1501 step=1pm speed=10 channels=1,2")
    scanner = MagicMock()
    scanner.run_stsprocess_scan.return_value = _fake_result(channels=(1, 2))
    run_job(job, scanner, tmp_path, timestamp="t")

    csv_file = next(tmp_path.rglob("01_a_fwd.csv"))
    lines = csv_file.read_text().strip().splitlines()
    assert lines[0] == "wavelength_nm,ch1_power_dbm,ch2_power_dbm,monitor_dbm"
    assert len(lines) == 1 + 3


def test_stops_on_error_by_default(tmp_path):
    job = parse_job(
        "scan a 1500 1501 step=1pm speed=10\nscan b 1500 1501 step=1pm speed=10\n"
    )
    scanner = MagicMock()
    scanner.run_stsprocess_scan.side_effect = [RuntimeError("boom"), _fake_result()]
    results = run_job(job, scanner, tmp_path, timestamp="t")

    assert scanner.run_stsprocess_scan.call_count == 1
    assert results[0].ok is False and "boom" in results[0].error


def test_keep_going_continues_after_error(tmp_path):
    job = parse_job(
        "scan a 1500 1501 step=1pm speed=10\nscan b 1500 1501 step=1pm speed=10\n"
    )
    scanner = MagicMock()
    scanner.run_stsprocess_scan.side_effect = [RuntimeError("boom"), _fake_result()]
    results = run_job(job, scanner, tmp_path, timestamp="t", keep_going=True)

    assert scanner.run_stsprocess_scan.call_count == 2
    assert results[0].ok is False and results[1].ok is True


def test_manifest_contents(tmp_path):
    job = parse_job("job jobA\nscan a 1500 1501 step=1pm speed=10")
    run_job(job, _scanner(), tmp_path, timestamp="ts")

    manifest = json.loads((tmp_path / "jobA_ts" / "manifest.json").read_text())
    assert manifest["job"] == "jobA"
    assert manifest["timestamp"] == "ts"
    assert len(manifest["segments"]) == 1
    seg = manifest["segments"][0]
    assert seg["label"] == "a"
    assert seg["direction"] == "fwd"
    assert seg["ok"] is True
    assert seg["csv"] == "01_a_fwd.csv"
    assert seg["start_wl"] == 1500.0 and seg["stop_wl"] == 1501.0
