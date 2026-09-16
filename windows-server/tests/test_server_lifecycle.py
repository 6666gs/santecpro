"""HTTP lifecycle tests: no hardware or DLL loading."""
import threading
from unittest.mock import Mock

import pytest
import server
from santec_dll_backend.instruments import ScanCancelled


@pytest.fixture
def instruments(monkeypatch):
    server.alignment_meter.close()
    laser, meter = Mock(), Mock()
    laser.idn.return_value, meter.idn.return_value = "TSL test", "MPM test"
    laser.laser_is_on.return_value = True
    monkeypatch.setattr(server, "DllTsl", Mock(return_value=laser))
    monkeypatch.setattr(server, "DllMpm", Mock(return_value=meter))
    server.laser_start_requests.clear()
    server.scan_cancel.clear()
    server._set_scan_state(running=False, phase="idle")
    yield laser, meter
    server.alignment_meter.close()


def test_prepare_waits_for_real_ready_and_sends_on_only_once(instruments):
    laser, _ = instruments
    laser.laser_is_on.side_effect = [False, False, False, True]
    with server.app.test_client() as client:
        assert client.post('/api/dll/laser/prepare').json['ready'] is False
        assert client.post('/api/dll/laser/prepare').json['ready'] is False
        laser.shutter_open.assert_not_called()
        assert client.post('/api/dll/laser/prepare').json['ready'] is True
    laser.laser_on.assert_called_once()
    laser.shutter_open.assert_called_once()
    laser.laser_off.assert_not_called()


def test_already_on_is_not_restarted(instruments):
    laser, _ = instruments
    with server.app.test_client() as client:
        assert client.post('/api/dll/laser/prepare').json['ready']
    laser.laser_on.assert_not_called()
    laser.laser_off.assert_not_called()


def test_probe_is_read_only_and_respects_addresses(instruments):
    laser, _ = instruments
    with server.app.test_client() as client:
        response = client.post('/api/dll/check', json={'tsl_address': 'GPIB1::2::INSTR', 'mpm_address': 'GPIB1::3::INSTR'})
    assert response.status_code == 200
    assert response.json['tsl_idn'] == 'TSL test'
    server.DllTsl.assert_called_once_with('GPIB1::2::INSTR')
    server.DllMpm.assert_called_once_with('GPIB1::3::INSTR')
    laser.laser_on.assert_not_called()
    laser.shutter_open.assert_not_called()


def test_cancel_remains_responsive_and_competing_scan_is_rejected(monkeypatch, instruments):
    entered = threading.Event()
    def scan(settings, cancel_event):
        entered.set()
        assert cancel_event.wait(3), 'cancel endpoint blocked on instrument lock'
        raise ScanCancelled('Scan cancelled')
    monkeypatch.setattr(server, 'run_stsprocess_scan', scan)
    responses = []
    def request_scan():
        with server.app.test_client() as client:
            responses.append(client.post('/api/scan/stsprocess', json={'start_wl':1540, 'stop_wl':1541,'step':.01,'speed':1}))
    thread = threading.Thread(target=request_scan)
    thread.start()
    try:
        assert entered.wait(3)
        with server.app.test_client() as client:
            assert client.post('/api/scan/stsprocess', json={}).status_code == 409
            assert client.post('/api/dll/laser/prepare').status_code == 409
            assert client.get('/api/scan/state').json['running']
            assert client.post('/api/scan/cancel').status_code == 202
    finally:
        server.scan_cancel.set()
        thread.join(3)
    assert not thread.is_alive()
    assert responses[0].json['cancelled'] is True
    assert server.scan_state['phase'] == 'cancelled'
    instruments[0].laser_off.assert_not_called()


def test_configuration_defaults_reach_scan(monkeypatch):
    from stsprocess_api import build_sts_scan_settings
    monkeypatch.setattr(server.config, 'TSL_ADDRESS', 'GPIB2::4::INSTR')
    monkeypatch.setattr(server.config, 'MPM_ADDRESS', 'GPIB2::5::INSTR')
    settings = build_sts_scan_settings(dict(start_wl=1540,stop_wl=1541,step=.01,speed=1), '.')
    assert settings.tsl_resource == 'GPIB2::4::INSTR'
    assert settings.mpm_resource == 'GPIB2::5::INSTR'


def test_alignment_sets_wavelength_power_and_auto_read_range(instruments):
    laser, meter = instruments
    meter.read_power_channels.return_value = {1: -12.3, 2: -13.4}
    with server.app.test_client() as client:
        response = client.post('/api/dll/alignment/start', json={
            'wavelength': 1560.5, 'power': -10, 'mpm_channels': [1, 2], 'mpm_range': 5})
    assert response.status_code == 200
    assert response.json['range_mode'] == 'auto'
    assert response.json['wavelength'] == 1560.5
    laser.set_wavelength_nm.assert_called_once_with(1560.5)
    laser.set_power_dbm.assert_called_once_with(-10)
    meter.configure_alignment.assert_called_once_with(1560.5)
    meter.configure_power_logging.assert_not_called()
    laser.laser_on.assert_not_called()
    laser.laser_off.assert_not_called()
    laser.shutter_open.assert_not_called()
    laser.disconnect.assert_called_once()
    meter.disconnect.assert_not_called()
    with server.app.test_client() as client:
        for _ in range(5):
            assert client.post("/api/dll/mpm/powers", json={"mpm_channels": [1, 2]}).status_code == 200
    meter.connect.assert_called_once()
    assert meter.read_power_channels.call_count == 6
    meter.configure_alignment.assert_called_once()
    server.alignment_meter.close()
    meter.disconnect.assert_called_once()


@pytest.mark.parametrize('payload', [{'power': 'nan'}, {'wavelength': -1}, {'wavelength': 'inf'},
                                     {'mpm_channels': []}, {'mpm_channels': [5]}, {'mpm_module': 'bad'}])
def test_alignment_rejects_invalid_settings_before_connect(instruments, payload):
    laser, meter = instruments
    with server.app.test_client() as client:
        response = client.post('/api/dll/alignment/start', json=payload)
    assert response.status_code == 400
    laser.connect.assert_not_called()
    meter.connect.assert_not_called()


def test_alignment_failure_disconnects_and_does_not_toggle_laser(instruments):
    laser, meter = instruments
    meter.configure_alignment.side_effect = RuntimeError('auto mode failed')
    with server.app.test_client() as client:
        response = client.post('/api/dll/alignment/start', json={'wavelength': 1550, 'power': 0})
    assert response.status_code == 500
    meter.read_power_channels.assert_not_called()
    laser.disconnect.assert_called_once()
    meter.disconnect.assert_called_once()
    laser.laser_off.assert_not_called()


def test_official_auto_range_and_nm_calls():
    from santec_dll_backend.instruments import DllMpm, DllTsl
    from types import SimpleNamespace
    meter = DllMpm.__new__(DllMpm)
    sdk = Mock()
    meter._mpm = sdk
    sdk.Power_Unit = SimpleNamespace(dBm=0)
    sdk.READ_Range_Mode = SimpleNamespace(Auto=1, Manual=0)
    for name in ('Set_Unit', 'Set_Wavelength', 'Set_READ_Range_Mode', 'Set_Range', 'Set_Range_Each_Channel'):
        getattr(sdk, name).return_value = 0
    meter.configure_alignment(1545)
    sdk.Set_READ_Range_Mode.assert_called_once_with(1)
    sdk.Set_Wavelength.assert_called_once_with(1545)
    sdk.Set_Range.assert_not_called()
    meter.configure_power_logging(0, 1, 3)  # subsequent sweep explicitly restores manual range
    assert sdk.Set_READ_Range_Mode.call_args.args == (0,)
    sdk.Set_Range.assert_called_once_with(3)
    laser = DllTsl.__new__(DllTsl)
    laser._tsl = Mock()
    laser._tsl.Wavelength_Unit = SimpleNamespace(nm=0)
    laser._tsl.Set_Wavelength_Unit.return_value = laser._tsl.Set_Wavelength.return_value = 0
    laser.set_wavelength_nm(1545)
    laser._tsl.Set_Wavelength_Unit.assert_called_once_with(0)
    laser._tsl.Set_Wavelength.assert_called_once_with(1545)


def test_scan_or_instrument_command_releases_alignment_connection(instruments):
    laser, meter = instruments
    meter.read_power_channels.return_value = {1: -5}
    with server.app.test_client() as client:
        assert client.post('/api/dll/alignment/start').status_code == 200
        meter.disconnect.assert_not_called()
        assert client.post('/api/dll/check').status_code == 200
    # The cached handle is released before the instrument check opens another handle.
    assert meter.disconnect.call_count == 2
    assert server.alignment_meter.meter is None


def test_failed_cached_read_releases_connection(instruments):
    _, meter = instruments
    meter.read_power_channels.return_value = {1: -5}
    with server.app.test_client() as client:
        assert client.post('/api/dll/alignment/start').status_code == 200
        meter.read_power_channels.side_effect = RuntimeError('bus error')
        assert client.post('/api/dll/mpm/powers').status_code == 500
    meter.disconnect.assert_called_once()
    assert server.alignment_meter.meter is None
