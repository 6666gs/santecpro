"""Regression: older MPM firmware must use measured NI DAQ data, not Get_216."""
from unittest.mock import Mock
from threading import Event
import pytest
from test_dll_stsprocess_scanner import FakeTsl, FakeMpm, FakeSts
from santec_dll_backend.scanner import STSScanSettings, run_stsprocess_scan
from santecpro.exceptions import ScanCancelled


def equipment():
    tsl, mpm, sts = FakeTsl(), FakeMpm(), FakeSts()
    spu = Mock()
    spu.get_sampling_raw_data.return_value = ([float(i) for i in range(1006)], [0.5]*1006)
    mpm.get_trigger_data = Mock(side_effect=RuntimeError('Get_216 code -20'))
    mpm.get_216_monitor_data = Mock(side_effect=RuntimeError('Get_216 code -20'))
    mpm.set_sts_logging_parameters = Mock()
    mpm.get_averaging_time_ms = Mock(return_value=.02)
    sts.set_spu_rescaling = Mock()
    sts.set_tsl_monitor_rescaling = Mock()
    return tsl, mpm, sts, spu


def settings(tmp_path):
    return STSScanSettings(1540,1540.1,.0001,1,daq_device='Dev1',csv_path=tmp_path/'result.csv')


def test_spu_path_arms_before_trigger_and_bypasses_unsupported_mpm(tmp_path):
    tsl, mpm, sts, spu = equipment()
    def trigger():
        spu.start_sampling.assert_called_once()
    tsl.soft_trigger = trigger
    result = run_stsprocess_scan(settings(tmp_path), tsl=tsl,mpm=mpm,sts=sts,spu=spu)
    assert result.target_points == 1001
    assert result.averaging_time_ms == .02
    assert (tmp_path/'result.csv').exists()
    assert mpm.set_sts_logging_parameters.call_args.args[3] == 0
    sts.set_spu_rescaling.assert_called_once_with(.02)
    sts.set_tsl_monitor_rescaling.assert_not_called()
    mpm.get_trigger_data.assert_not_called()
    mpm.get_216_monitor_data.assert_not_called()
    spu.configure.assert_called_once_with(1540,1540.1,1,.001,.02)
    spu.disconnect.assert_called_once()


def test_spu_failure_does_not_fall_back_or_write_csv(tmp_path):
    tsl, mpm, sts, spu = equipment()
    spu.get_sampling_raw_data.side_effect = RuntimeError('missing trigger')
    with pytest.raises(RuntimeError, match='missing trigger'):
        run_stsprocess_scan(settings(tmp_path),tsl=tsl,mpm=mpm,sts=sts,spu=spu)
    assert not (tmp_path/'result.csv').exists()
    assert tsl.disconnected and mpm.disconnected
    spu.stop_sampling.assert_called_once()
    spu.disconnect.assert_called_once()
    mpm.get_trigger_data.assert_not_called()


def test_spu_cancel_cleans_all_devices(tmp_path):
    tsl, mpm, sts, spu = equipment()
    cancel = Event()
    tsl.soft_trigger = cancel.set
    with pytest.raises(ScanCancelled):
        run_stsprocess_scan(settings(tmp_path),tsl=tsl,mpm=mpm,sts=sts,spu=spu,cancel_event=cancel)
    spu.stop_sampling.assert_called_once()
    spu.disconnect.assert_called_once()
    assert not (tmp_path/'result.csv').exists()


def test_spu_wrapper_uses_void_configuration_and_async_sampling():
    from santec_dll_backend.instruments import DllSpu
    device = DllSpu.__new__(DllSpu)
    device._spu = Mock()
    device._spu.Set_Sampling_Parameter.return_value = None
    device._spu.Sampling_Start.return_value = 0
    device._spu.IsSampling = False
    device._spu.Logging_Errorcode = 0
    device.configure(1500, 1630, 20, .001, .01)
    assert device._spu.AveragingTime == .01
    device.start_sampling()
    device._spu.Sampling_Start.assert_called_once_with(True)
    device.wait_for_completion(.1)
    device._spu.Logging_Errorcode = -1
    with pytest.raises(RuntimeError, match='SPU sampling'):
        device.wait_for_completion(.1)


def test_spu_wait_is_cancellable_and_bounded():
    from santec_dll_backend.instruments import DllSpu
    device = DllSpu.__new__(DllSpu)
    device._spu = Mock(IsSampling=True)
    with pytest.raises(TimeoutError):
        device.wait_for_completion(0)
    cancel = Event()
    cancel.set()
    with pytest.raises(ScanCancelled):
        device.wait_for_completion(100, cancel_event=cancel)


def test_daq_settings_come_from_windows_config(monkeypatch):
    import config
    from stsprocess_api import build_sts_scan_settings
    monkeypatch.setattr(config, 'DAQ_DEVICE', 'Dev1')
    settings = build_sts_scan_settings(dict(start_wl=1500,stop_wl=1630,step=.001,speed=20), '.')
    assert settings.daq_device == 'Dev1'
