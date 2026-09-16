from types import SimpleNamespace
from threading import Event
from unittest.mock import Mock
import pytest
from santec_dll_backend.instruments import DllTsl, ScanCancelled


def make_tsl():
    tsl = DllTsl.__new__(DllTsl)
    statuses = SimpleNamespace(Standby=0, Running=1, Pausing=2, WaitingforTrigger=3, Returning=4)
    tsl._tsl = SimpleNamespace(Sweep_Status=statuses, Get_Sweep_Status=Mock(return_value=(0, 0)),
                               LD_Status=SimpleNamespace(LD_OFF=0, LD_ON=1), Get_LD_Status=Mock(return_value=(0, 0)))
    return tsl


def test_ld_readiness_uses_readback():
    tsl = make_tsl()
    assert not tsl.laser_is_on()
    tsl._tsl.Get_LD_Status.return_value = (0, 1)
    assert tsl.laser_is_on()


def test_cancelled_wait_does_not_block_in_dll():
    tsl = make_tsl()
    event = Event()
    event.set()
    with pytest.raises(ScanCancelled):
        tsl.wait_for_status(3000, 'standby', event)
    tsl._tsl.Get_Sweep_Status.assert_not_called()


def test_status_poll_checks_timeout_and_error():
    tsl = make_tsl()
    tsl.wait_for_status(0, 'standby')
    with pytest.raises(TimeoutError):
        tsl.wait_for_status(0, 'running')
    tsl._tsl.Get_Sweep_Status.return_value = (-123, 0)
    with pytest.raises(RuntimeError, match='Get_Sweep_Status'):
        tsl.wait_for_status(0, 'standby')


def test_mpm_waits_for_all_points(monkeypatch):
    from santec_dll_backend.instruments import DllMpm
    mpm = DllMpm.__new__(DllMpm)
    mpm._mpm = SimpleNamespace(Get_Logging_Status=Mock(side_effect=[(0, 0, 2), (0, 1, 10)]))
    monkeypatch.setattr('santec_dll_backend.instruments.time.sleep', lambda _: None)
    assert mpm.wait_for_log_completion(expected_points=10) == (1, 10)
    mpm._mpm.Get_Logging_Status = Mock(return_value=(0, 0, 2))
    with pytest.raises(TimeoutError, match='Incomplete'):
        mpm.wait_for_log_completion(expected_points=10, timeout_s=0)


def test_mpm_error_not_hidden_by_status_minus_one():
    from santec_dll_backend.instruments import DllMpm
    mpm = DllMpm.__new__(DllMpm)
    mpm._mpm = SimpleNamespace(Get_Logging_Status=Mock(return_value=(-2, -1, 10)))
    with pytest.raises(RuntimeError, match='Get_Logging_Status'):
        mpm.wait_for_log_completion(expected_points=10)
