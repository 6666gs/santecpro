"""Tests for Windows STSProcess API request/response helpers."""

from __future__ import annotations

from stsprocess_api import build_sts_scan_settings, sts_scan_result_to_dict


def test_build_sts_scan_settings_uses_scan_jobs_csv_directory():
    settings = build_sts_scan_settings({
        "start_wl": 1540.0,
        "stop_wl": 1540.0001,
        "step": 0.0001,
        "speed": 1.0,
        "power": 0.0,
        "mpm_module": 0,
        "mpm_channel": 1,
        "mpm_channels": [1, 2],
        "mpm_range": 1,
        "csv_name": "scan.csv",
    }, base_dir=r"E:\code_pro\windows_server")

    assert settings.start_wl == 1540.0
    assert settings.step == 0.0001
    assert settings.power == 0.0
    assert settings.mpm_channels == (1, 2)
    assert str(settings.csv_path).endswith(r"scan_jobs/scan.csv")


def test_sts_scan_result_to_dict_contains_rescaled_and_raw_metadata():
    class Result:
        wavelengths = [1540.0, 1540.0001]
        powers = [-10.0, -10.1]
        monitor_powers = [0.0, 0.0]
        channel_powers = {1: [-10.0, -10.1], 2: [-20.0, -20.1]}
        actual_step = 0.001
        requested_points = 2
        target_points = 2
        raw_points = 3
        mpm_expected_raw_points = 3
        mpm_completed_points = 3
        csv_path = r"E:\code_pro\windows_server\scan_jobs\scan.csv"
        tsl_idn = "TSL"
        mpm_idn = "MPM"
        averaging_time_ms = 0.02

    data = sts_scan_result_to_dict(Result(), {
        "mpm_averaging_time_ms": 0.01,
        "start_wl": 1540.0,
        "stop_wl": 1540.0001,
        "step": 0.0001,
        "speed": 1.0,
    })

    assert data["scan_params"]["mpm_averaging_time_ms"] == 0.02
    assert data["wavelengths"] == [1540.0, 1540.0001]
    assert data["channel_powers"] == {"1": [-10.0, -10.1], "2": [-20.0, -20.1]}
    assert data["raw_points"] == 3
    assert data["target_points"] == 2
    assert data["actual_step"] == 0.001
    assert data["scan_params"]["raw_points"] == 3
