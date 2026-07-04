"""Tests for the UI scan controller."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from santecpro.ui_controller import ConnectionSettings, ScanSettings, ScanUiController


def test_remote_controller_connects_and_runs_single_scan(monkeypatch):
    remote = MagicMock()
    remote.status.return_value = {"status": "running"}
    remote.run_stsprocess_scan.return_value = "scan-result"
    remote_cls = MagicMock(return_value=remote)
    monkeypatch.setattr("santecpro.ui_controller.RemoteScanner", remote_cls)

    controller = ScanUiController()
    conn = ConnectionSettings(
        mode="remote",
        server_url="http://192.168.100.103:5000",
        tsl_address="GPIB3::1::INSTR",
        mpm_address="GPIB0::16::INSTR",
    )
    scan = ScanSettings(
        start_wl=1550.0,
        stop_wl=1550.1,
        step=0.01,
        speed=1.0,
        power=0.0,
        sweep_mode=1,
        mpm_range=1,
        mpm_module=0,
        mpm_channel=1,
        mpm_averaging_time_ms=0.01,
        mpm_channels=(1, 2),
    )

    status = controller.connect(conn)
    result = controller.run_single_scan(scan)

    remote_cls.assert_called_once_with("http://192.168.100.103:5000")
    remote.connect.assert_not_called()
    remote.status.assert_called_once_with()
    assert status == {"status": "running"}
    remote.configure.assert_not_called()
    remote.run_stsprocess_scan.assert_called_once_with(
        start_wl=1550.0,
        stop_wl=1550.1,
        step=0.01,
        speed=1.0,
        power=0.0,
        mpm_module=0,
        mpm_channel=1,
        mpm_channels=(1, 2),
        mpm_range=1,
        mpm_averaging_time_ms=0.01,
        csv_name="",
        plot=False,
        save_csv=None,
    )
    remote.run_single_scan.assert_not_called()
    assert result == "scan-result"


def test_local_controller_connects_and_runs_single_scan(monkeypatch):
    resource_manager = MagicMock()
    pyvisa_module = MagicMock(ResourceManager=MagicMock(return_value=resource_manager))
    tsl = MagicMock()
    mpm = MagicMock()
    scanner = MagicMock()
    scanner.run_single_scan.return_value = "local-result"

    monkeypatch.setattr("santecpro.ui_controller.pyvisa", pyvisa_module)
    monkeypatch.setattr("santecpro.ui_controller.TSLInstrument", MagicMock(return_value=tsl))
    monkeypatch.setattr("santecpro.ui_controller.MPMInstrument", MagicMock(return_value=mpm))
    monkeypatch.setattr("santecpro.ui_controller.Scanner", MagicMock(return_value=scanner))

    controller = ScanUiController()
    conn = ConnectionSettings(
        mode="local",
        server_url="",
        tsl_address="GPIB3::1::INSTR",
        mpm_address="GPIB0::16::INSTR",
    )
    scan = ScanSettings(
        start_wl=1550.0,
        stop_wl=1550.1,
        step=0.01,
        speed=1.0,
        power=0.0,
        sweep_mode=1,
        mpm_range=1,
        mpm_module=0,
        mpm_channel=1,
        mpm_averaging_time_ms=0.01,
    )

    status = controller.connect(conn)
    result = controller.run_single_scan(scan)

    pyvisa_module.ResourceManager.assert_called_once()
    tsl.connect.assert_called_once_with("GPIB3::1::INSTR")
    mpm.connect.assert_called_once_with("GPIB0::16::INSTR")
    scanner.configure.assert_called_once_with(
        start_wl=1550.0,
        stop_wl=1550.1,
        step=0.01,
        speed=1.0,
        power=0.0,
        sweep_mode=1,
        ranges=[1],
        mpm_module=0,
        mpm_channel=1,
        mpm_averaging_time_ms=0.01,
    )
    scanner.run_single_scan.assert_called_once_with(
        mpm_range=1, plot=False, save_csv=None
    )
    assert status["mode"] == "local"
    assert result == "local-result"


def test_controller_rejects_scan_before_connect():
    controller = ScanUiController()
    settings = ScanSettings(
        start_wl=1550.0,
        stop_wl=1550.1,
        step=0.01,
        speed=1.0,
        power=0.0,
        sweep_mode=1,
        mpm_range=1,
        mpm_module=0,
        mpm_channel=1,
        mpm_averaging_time_ms=0.01,
    )

    with pytest.raises(RuntimeError, match="Not connected"):
        controller.run_single_scan(settings)


def test_remote_controller_reads_alignment_powers(monkeypatch):
    remote = MagicMock()
    remote.status.return_value = {"status": "running"}
    remote.start_alignment.return_value = {1: -10.0, 2: -11.0}
    remote.read_alignment_powers.return_value = {1: -9.5, 2: -10.5}
    monkeypatch.setattr("santecpro.ui_controller.RemoteScanner", MagicMock(return_value=remote))

    controller = ScanUiController()
    controller.connect(ConnectionSettings(
        mode="remote",
        server_url="http://192.168.100.103:5000",
        tsl_address="",
        mpm_address="",
    ))

    assert controller.start_alignment(0.0, 0, (1, 2), 1) == {1: -10.0, 2: -11.0}
    assert controller.read_alignment_powers(0, (1, 2)) == {1: -9.5, 2: -10.5}
