"""HTTP lifecycle tests: no hardware or DLL loading."""
import threading
from unittest.mock import Mock

import pytest
import server
from santec_dll_backend.instruments import ScanCancelled


@pytest.fixture
def instruments(monkeypatch):
    laser, meter = Mock(), Mock()
    laser.idn.return_value, meter.idn.return_value = "TSL test", "MPM test"
    laser.laser_is_on.return_value = True
    monkeypatch.setattr(server, "DllTsl", Mock(return_value=laser))
    monkeypatch.setattr(server, "DllMpm", Mock(return_value=meter))
    server.laser_start_requests.clear()
    server.scan_cancel.clear()
    server._set_scan_state(running=False, phase="idle")
    return laser, meter


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
