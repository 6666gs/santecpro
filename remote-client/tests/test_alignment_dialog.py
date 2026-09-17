"""Alignment controls and worker lifecycle; no real instrument commands."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from threading import Event
from unittest.mock import Mock
from PyQt5.QtWidgets import QApplication
from santecpro.ui_app import AlignmentDialog
from santecpro.remote import RemoteScanner
from test_ui_script import pump
import pytest


def test_edit_apply_stop_and_close_keeps_laser_on():
    app = QApplication.instance() or QApplication([])
    controller = Mock()
    controller.start_alignment.return_value = {1: -10.5}
    controller.read_alignment_powers.return_value = {1: -9.8}
    dialog = AlignmentDialog(controller, 0, 0, (1,), 5, wavelength=1550)
    dialog.show()
    try:
        assert dialog.isModal()
        dialog.wavelength_spin.setValue(1560.5)
        dialog.power_spin.setValue(-10)
        dialog._start()
        pump(app, lambda: dialog._thread is None)
        controller.start_alignment.assert_called_once_with(-10, 0, (1,), wavelength=1560.5)
        assert '-10.500' in dialog._labels[1].text()
        dialog.wavelength_spin.setValue(1548)
        dialog._start()
        pump(app, lambda: dialog._thread is None)
        assert controller.start_alignment.call_args.kwargs == {'wavelength': 1548}
        dialog._poll()
        pump(app, lambda: dialog._thread is None)
        assert '-9.800' in dialog._labels[1].text()
        dialog._stop()
        assert not dialog._timer.isActive()
        controller.laser_off.assert_not_called()
    finally:
        dialog.close()


def test_close_defers_until_inflight_request_finishes():
    app = QApplication.instance() or QApplication([])
    entered, release = Event(), Event()
    controller = Mock()
    def start(*args, **kwargs):
        entered.set()
        release.wait(3)
        return {1: -12}
    controller.start_alignment.side_effect = start
    dialog = AlignmentDialog(controller, 0, 0, (1,), 1)
    dialog.show()
    dialog._start()
    pump(app, entered.is_set)
    dialog.reject()  # Escape must not destroy a running QThread or allow parent scans
    assert dialog.isVisible() and dialog._closing
    release.set()
    pump(app, lambda: dialog._thread is None and not dialog.isVisible())
    assert not dialog._timer.isActive()
    controller.laser_off.assert_not_called()


def test_error_stops_polling_and_reports_failure():
    app = QApplication.instance() or QApplication([])
    controller = Mock()
    controller.start_alignment.side_effect = RuntimeError('auto failed')
    dialog = AlignmentDialog(controller, 0, 0, (1,), 1)
    dialog._start()
    pump(app, lambda: dialog._thread is None)
    assert 'auto failed' in dialog.state_label.text()
    assert not dialog._timer.isActive()
    dialog.close()


def test_remote_alignment_requires_server_support():
    scanner = RemoteScanner.__new__(RemoteScanner)
    scanner._post = Mock(return_value={'range_mode': 'auto', 'wavelength': 1545, 'powers': {'1': -3}})
    assert scanner.start_alignment(-10, wavelength=1545) == {1: -3}
    payload = scanner._post.call_args.args[1]
    assert payload['wavelength'] == 1545 and 'mpm_range' not in payload
    scanner._post.return_value = {'powers': {'1': -3}}
    with pytest.raises(RuntimeError, match='Windows'):
        scanner.start_alignment(-10, wavelength=1545)


def test_refresh_budget_and_apply_during_inflight_read():
    app = QApplication.instance() or QApplication([])
    entered, release = Event(), Event()
    controller = Mock()
    controller.start_alignment.return_value = {1: -10}
    def read(*args):
        entered.set()
        release.wait(3)
        return {1: -9}
    controller.read_alignment_powers.side_effect = read
    dialog = AlignmentDialog(controller, 0, 0, (1,), 1)
    dialog._start()
    pump(app, lambda: dialog._thread is None)
    assert 0 < dialog._timer.interval() <= 100
    dialog._poll()
    pump(app, entered.is_set)
    assert dialog.start_btn.isEnabled()
    dialog.power_spin.setValue(-5)
    dialog._start()
    assert dialog._apply_pending
    controller.start_alignment.assert_called_once()
    release.set()
    pump(app, lambda: controller.start_alignment.call_count == 2 and dialog._thread is None)
    assert controller.start_alignment.call_args.args[0] == -5
    dialog.close()


def test_successful_applied_settings_persist_across_dialogs(tmp_path):
    from PyQt5.QtCore import QSettings
    app = QApplication.instance() or QApplication([])
    path = str(tmp_path / 'preferences.ini')
    prefs = QSettings(path, QSettings.IniFormat)
    controller = Mock()
    controller.start_alignment.return_value = {1: -10}
    dialog = AlignmentDialog(controller, 0, 0, (1,), 1, wavelength=1500, preferences=prefs)
    dialog.wavelength_spin.setValue(1560.25)
    dialog.power_spin.setValue(-7.5)
    dialog._start()
    pump(app, lambda: dialog._thread is None)
    # Unapplied edits do not replace actual last-applied settings.
    dialog.wavelength_spin.setValue(1570)
    dialog.power_spin.setValue(-3)
    dialog.close()
    prefs2 = QSettings(path, QSettings.IniFormat)
    reopened = AlignmentDialog(controller, 10, 0, (1,), 1, wavelength=1600, preferences=prefs2)
    assert reopened.wavelength_spin.value() == 1560.25
    assert reopened.power_spin.value() == -7.5
    controller.start_alignment.assert_called_once()  # opening does not send commands
    controller.start_alignment.side_effect = RuntimeError('rejected')
    reopened.power_spin.setValue(-2)
    reopened._start()
    pump(app, lambda: reopened._thread is None)
    assert float(prefs2.value('alignment/power_dbm')) == -7.5
    reopened.close()


def test_invalid_saved_settings_fall_back_to_initial_values(tmp_path):
    from PyQt5.QtCore import QSettings
    app = QApplication.instance() or QApplication([])
    prefs = QSettings(str(tmp_path / 'bad.ini'), QSettings.IniFormat)
    prefs.setValue('alignment/wavelength_nm', 'nan')
    prefs.setValue('alignment/power_dbm', 'bad')
    dialog = AlignmentDialog(Mock(), -4, 0, (1,), 1, wavelength=1540, preferences=prefs)
    assert dialog.wavelength_spin.value() == 1540 and dialog.power_spin.value() == -4
    dialog.close()


def test_busy_reads_retry_automatically_without_reapplying_laser():
    from santecpro.exceptions import InstrumentsBusyError
    app = QApplication.instance() or QApplication([])
    controller = Mock()
    controller.start_alignment.return_value = {1: -10}
    controller.read_alignment_powers.side_effect = [InstrumentsBusyError('busy'), InstrumentsBusyError('busy'), {1: -8}]
    dialog = AlignmentDialog(controller, 0, 0, (1,), 1)
    try:
        dialog._start()
        pump(app, lambda: dialog._thread is None)
        dialog._poll()
        pump(app, lambda: dialog._thread is None)
        assert dialog._monitoring and dialog._timer.isActive()
        assert dialog._timer.interval() == 250
        assert '等待' in dialog._labels[1].text()
        pump(app, lambda: controller.read_alignment_powers.call_count >= 3 and dialog._thread is None)
        assert '-8.000' in dialog._labels[1].text()
        assert dialog._busy_count == 0
        assert dialog._timer.interval() <= 100
        controller.start_alignment.assert_called_once()
    finally:
        dialog.close()


def test_busy_apply_retries_original_settings_and_stop_cancels_retry():
    from santecpro.exceptions import InstrumentsBusyError
    app = QApplication.instance() or QApplication([])
    controller = Mock()
    controller.start_alignment.side_effect = [InstrumentsBusyError('busy'), {1: -10}]
    dialog = AlignmentDialog(controller, -5, 0, (1,), 1, wavelength=1550)
    try:
        dialog._start()
        pump(app, lambda: dialog._thread is None)
        dialog.power_spin.setValue(-9)  # Unapplied edit must not affect retry.
        pump(app, lambda: controller.start_alignment.call_count == 2 and dialog._thread is None)
        assert controller.start_alignment.call_args.args[0] == -5
        controller.read_alignment_powers.side_effect = InstrumentsBusyError('busy')
        dialog._poll()
        pump(app, lambda: dialog._thread is None)
        dialog._stop()
        assert not dialog._timer.isActive() and dialog._retry_task is None
        dialog._poll()
        assert controller.read_alignment_powers.call_count == 1
        controller.laser_off.assert_not_called()
    finally:
        dialog.close()


@pytest.mark.parametrize('payload,expected', [
    ({'error':'Instruments are busy.'}, 'busy'),
    ({'error':'occupied','code':'instruments_busy'}, 'busy'),
    ({'error':'different conflict'}, 'error'),
    ({'error':'cancelled','cancelled':True}, 'cancel'),
])
def test_http_busy_is_distinct_from_other_errors(monkeypatch, payload, expected):
    from santecpro.exceptions import InstrumentsBusyError, ScanCancelled
    response = Mock(status_code=409)
    response.json.return_value = payload
    monkeypatch.setattr('santecpro.remote.requests.post', Mock(return_value=response))
    scanner = RemoteScanner('http://unused')
    cls = {'busy':InstrumentsBusyError,'error':RuntimeError,'cancel':ScanCancelled}[expected]
    with pytest.raises(cls) as exc:
        scanner.read_alignment_powers(0, (1,))
    if expected == 'error': assert not isinstance(exc.value, InstrumentsBusyError)
