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
