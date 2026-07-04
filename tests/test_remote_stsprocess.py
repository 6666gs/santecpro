"""Tests for remote STSProcess scan client behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from santecpro.remote import RemoteScanner
from santecpro.scanner import ScanResult


def test_remote_scanner_posts_stsprocess_scan_and_builds_result(monkeypatch):
    post = MagicMock()
    post.return_value.raise_for_status.return_value = None
    post.return_value.json.return_value = {
        "wavelengths": [1540.0, 1540.0001],
        "powers": [-10.0, -10.1],
        "monitor_powers": [0.0, 0.0],
        "scan_params": {"step": 0.0001},
        "timestamp": "2026-04-27T00:00:00+00:00",
        "mpm_range": 1,
        "csv_path": r"E:\code_pro\windows_server\scan_jobs\scan.csv",
        "raw_points": 3,
        "actual_step": 0.001,
    }
    monkeypatch.setattr("santecpro.remote.requests.post", post)

    scanner = RemoteScanner("http://192.168.100.103:5000")
    result = scanner.run_stsprocess_scan(
        start_wl=1540.0,
        stop_wl=1540.0001,
        step=0.0001,
        speed=1.0,
        power=0.0,
        mpm_module=0,
        mpm_channel=1,
        mpm_range=1,
        csv_name="scan.csv",
        plot=False,
    )

    post.assert_called_once_with(
        "http://192.168.100.103:5000/api/scan/stsprocess",
        json={
            "start_wl": 1540.0,
            "stop_wl": 1540.0001,
            "step": 0.0001,
            "speed": 1.0,
            "power": 0.0,
            "mpm_module": 0,
            "mpm_channel": 1,
            "mpm_range": 1,
            "mpm_averaging_time_ms": 0.01,
            "csv_name": "scan.csv",
        },
        timeout=300.0,
    )
    assert isinstance(result, ScanResult)
    np.testing.assert_allclose(result.wavelengths, [1540.0, 1540.0001])
    np.testing.assert_allclose(result.powers, [-10.0, -10.1])
    assert result.scan_params["csv_path"] == r"E:\code_pro\windows_server\scan_jobs\scan.csv"
    assert result.scan_params["raw_points"] == 3
    assert result.scan_params["actual_step"] == 0.001


def test_remote_laser_controls_use_dll_routes(monkeypatch):
    post = MagicMock()
    post.return_value.raise_for_status.return_value = None
    post.return_value.json.return_value = {"status": "ok"}
    monkeypatch.setattr("santecpro.remote.requests.post", post)

    scanner = RemoteScanner("http://192.168.100.103:5000")
    scanner.laser_on()
    scanner.laser_off()

    assert post.call_args_list[0].args[0] == "http://192.168.100.103:5000/api/dll/laser/on"
    assert post.call_args_list[1].args[0] == "http://192.168.100.103:5000/api/dll/laser/off"
