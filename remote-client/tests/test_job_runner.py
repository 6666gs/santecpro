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
    assert (job_dir / "01_a_fwd_raw.csv").exists()
    assert (job_dir / "02_b_rev_raw.csv").exists()
    assert (job_dir / "manifest.json").exists()
    assert all(r.ok for r in results)
    assert results[0].points == 3


def test_csv_has_header_and_rows(tmp_path):
    job = parse_job("scan a 1500 1501 step=1pm speed=10 channels=1,2")
    scanner = MagicMock()
    scanner.run_stsprocess_scan.return_value = _fake_result(channels=(1, 2))
    run_job(job, scanner, tmp_path, timestamp="t")

    csv_file = next(tmp_path.rglob("01_a_fwd_raw.csv"))
    lines = csv_file.read_text().strip().splitlines()
    assert lines[14] == "Wavelength(nm),Monitor-R1(dBm),Raw_M1-Ch1-R1(dBm),Raw_M1-Ch2-R1(dBm),,"
    assert len(lines) == 15 + 3


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
    assert seg["csv"] == "01_a_fwd_raw.csv"
    assert seg["start_wl"] == 1500.0 and seg["stop_wl"] == 1501.0


def test_cancel_stops_batch_even_with_keep_going(tmp_path):
    from santecpro.exceptions import ScanCancelled
    job = parse_job('scan a 1500 1501 step=1pm speed=10\nscan b 1500 1501 step=1pm speed=10')
    scanner = _scanner()
    scanner.run_stsprocess_scan.side_effect = ScanCancelled('cancelled')
    result = run_job(job, scanner, tmp_path, timestamp='t', keep_going=True)
    assert len(result) == 1
    assert not result[0].ok
    assert scanner.run_stsprocess_scan.call_count == 1


def test_interrupt_preserves_completed_manifest(tmp_path):
    import pytest
    job = parse_job('scan a 1500 1501 step=1pm speed=10\nscan b 1500 1501 step=1pm speed=10')
    scanner = _scanner()
    scanner.run_stsprocess_scan.side_effect = [_fake_result(), KeyboardInterrupt()]
    with pytest.raises(KeyboardInterrupt):
        run_job(job, scanner, tmp_path, timestamp='t')
    manifest = json.loads((tmp_path / 'job_t' / 'manifest.json').read_text())
    assert len(manifest['segments']) == 1
    assert manifest['segments'][0]['ok']


def test_batch_measures_reference_then_retains_raw_and_loss(tmp_path):
    from santecpro.session import ScanSession
    job = parse_job('scan reference 1500 1501 step=1pm speed=10\nscan device 1500 1501 step=1pm speed=10')
    session = ScanSession()
    results = run_job(job, _scanner(), tmp_path, timestamp='t', session=session,
                      reference_first=True, reference_ready=lambda: None, save_kind='loss')
    assert len(session.records) == 2
    assert results[0].record.is_reference
    assert not results[0].record.loss
    assert results[0].csv_path.endswith('_raw.csv')
    assert results[1].csv_path.endswith('_loss.csv')
    assert results[1].record.raw is not None
    np.testing.assert_array_equal(results[1].record.loss[1], [0, 0, 0])


def test_failed_reference_never_continues_batch(tmp_path):
    job = parse_job('scan reference 1500 1501 step=1pm speed=10\nscan device 1500 1501 step=1pm speed=10')
    scanner = _scanner()
    scanner.run_stsprocess_scan.side_effect = RuntimeError('reference failed')
    results = run_job(job, scanner, tmp_path, timestamp='t', reference_first=True, reference_ready=lambda: None, keep_going=True)
    assert len(results) == 1
    assert scanner.run_stsprocess_scan.call_count == 1


def test_wait_only_after_csv_and_manifest_saved(tmp_path):
    from pathlib import Path
    job = parse_job('device chip1\nscan wide 1500 1630 step=1pm speed=20\n'
                    'wait 5s\nscan fine 1545 1555 step=0.1pm speed=1')
    scanner = _scanner()
    def wait(seconds):
        assert seconds == 5
        assert scanner.run_stsprocess_scan.call_count == 1
        folder = tmp_path / 'job_t'
        assert (folder / 'chip1_01_wide_1500-1630nm_1pm_20nms_fwd_raw.csv').exists()
        manifest = json.loads((folder / 'manifest.json').read_text())
        assert manifest['device'] == 'chip1'
        assert manifest['segments'][0]['ok']
        assert manifest['segments'][0]['wait_after_s'] == 5
    results = run_job(job, scanner, tmp_path, timestamp='t', sleep=wait)
    assert len(results) == 2
    assert Path(results[1].csv_path).name == 'chip1_02_fine_1545-1555nm_0.1pm_1nms_fwd_raw.csv'
    assert scanner.run_stsprocess_scan.call_args.kwargs['step'] == 0.0001
    scanner.prepare_laser.assert_not_called()


def test_interrupt_during_wait_preserves_data_and_stops_next_scan(tmp_path):
    import pytest
    job = parse_job('scan a 1500 1501 step=1pm speed=10\nwait 5s\n'
                    'scan b 1500 1501 step=1pm speed=10')
    scanner = _scanner()
    def interrupt(seconds):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        run_job(job, scanner, tmp_path, timestamp='t', sleep=interrupt)
    assert scanner.run_stsprocess_scan.call_count == 1
    manifest = json.loads((tmp_path / 'job_t' / 'manifest.json').read_text())
    assert len(manifest['segments']) == 1
    assert manifest['segments'][0]['ok']


def test_existing_run_directory_is_never_overwritten(tmp_path):
    import pytest
    job = parse_job('scan a 1500 1501 step=1pm speed=10')
    scanner = _scanner()
    run_job(job, scanner, tmp_path, timestamp='t')
    with pytest.raises(FileExistsError):
        run_job(job, scanner, tmp_path, timestamp='t')
    assert scanner.run_stsprocess_scan.call_count == 1


def test_save_failure_stops_before_wait_and_next_scan(tmp_path, monkeypatch):
    import santecpro.job_runner as runner
    job = parse_job('scan a 1500 1501 step=1pm speed=10\nwait 5s\n'
                    'scan b 1500 1501 step=1pm speed=10')
    monkeypatch.setattr(runner, 'save_record_csv', MagicMock(side_effect=OSError('disk full')))
    scanner, sleep = _scanner(), MagicMock()
    results = run_job(job, scanner, tmp_path, timestamp='t', sleep=sleep)
    assert not results[0].ok
    sleep.assert_not_called()
    assert scanner.run_stsprocess_scan.call_count == 1
