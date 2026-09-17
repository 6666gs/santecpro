"""Script GUI sequencing tests with a fake instrument, real Qt worker/timer."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import time
from unittest.mock import MagicMock

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox, QScrollBar
from santecpro.ui_app import ScanMainWindow
from santecpro.results import ScanResult


def pump(app, condition, timeout=3):
    deadline = time.monotonic() + timeout
    while not condition():
        app.processEvents()
        if time.monotonic() > deadline:
            pytest.fail('Qt task did not reach expected state')
        time.sleep(.005)
    app.processEvents()


@pytest.fixture
def gui(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = ScanMainWindow(auto_connect=False)
    window._controller._scanner = MagicMock()
    window._controller.laser_ready = True
    raw = ScanResult(np.array([1550., 1551.]), np.array([-10., -11.]), np.array([7., 7.]))
    window._controller.run_single_scan = MagicMock(return_value=raw)
    window._controller.cancel_scan = MagicMock(return_value={})
    window.script_editor.setPlainText(f'device chip\noutput "{tmp_path}"\n'
        'scan wide 1500 1630 step=1pm speed=20\nwait 5s\n'
        'scan fine 1545 1555 step=0.1pm speed=1')
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: None)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: None)
    window.show()
    yield app, window
    if window._script_job is not None:
        window._cancel_scan()
    pump(app, lambda: window._thread is None and window._cancel_thread is None)
    window.close()


def test_shows_saves_then_pauses_and_continues(gui):
    app, w = gui
    w.script_review_check.setChecked(True)
    w._start_script()
    pump(app, lambda: w._script_timer.isActive())
    assert w._script_paused
    assert len(w._session.records) == w.history_combo.count() == 1
    assert w._last_record is w._session.records[0]
    assert w._controller.run_single_scan.call_count == 1
    assert list(w._script_dir.glob('*wide*raw.csv'))
    assert w.history_combo.isEnabled()
    assert not w.scan_btn.isEnabled()
    assert not w.laser_off_btn.isEnabled()
    assert not w.settings_button.isEnabled()
    w._script_clock -= 20
    w._script_tick()
    assert w._controller.run_single_scan.call_count == 1
    w._pause_script()  # continue immediately, no remaining wait
    pump(app, lambda: w._script_job is None and w._thread is None)
    assert w._controller.run_single_scan.call_count == 2
    assert len(w._session.records) == w.history_combo.count() == 2
    assert list(w._script_dir.glob('*fine*raw.csv'))
    manifest = json.loads((w._script_dir / 'manifest.json').read_text())
    assert len(manifest['segments']) == 2
    assert all(s['ok'] for s in manifest['segments'])
    assert w._controller.run_single_scan.call_args.args[0].step == .0001
    w._controller._scanner.prepare_laser.assert_not_called()
    w._controller._scanner.laser_off.assert_not_called()


def test_stop_wait_never_starts_next_scan_or_sends_remote_cancel(gui):
    app, w = gui
    w._start_script()
    pump(app, lambda: w._script_timer.isActive())
    w._cancel_scan()
    assert w._script_job is None
    assert not w._script_timer.isActive()
    assert w._controller.run_single_scan.call_count == 1
    w._controller.cancel_scan.assert_not_called()
    assert len(w._session.records) == 1


def test_countdown_automatically_starts_next_scan(gui):
    app, w = gui
    w._start_script()
    pump(app, lambda: w._script_timer.isActive())
    w._script_clock -= 6
    w._script_tick()
    pump(app, lambda: w._script_job is None and w._thread is None)
    assert w.history_combo.count() == 2


def test_save_error_keeps_curve_and_stops(gui, monkeypatch):
    app, w = gui
    monkeypatch.setattr('santecpro.ui_script.save_record_csv', MagicMock(side_effect=OSError('disk full')))
    w._start_script()
    pump(app, lambda: w._script_job is None and w._thread is None)
    assert w.history_combo.count() == 1
    assert w._controller.run_single_scan.call_count == 1
    manifest = json.loads((w._script_dir / 'manifest.json').read_text())
    assert not manifest['segments'][0]['ok']


def test_active_script_layout_fits_small_window(gui):
    app, w = gui
    w.resize(900, 560)
    w.script_review_check.setChecked(True)
    w._start_script()
    pump(app, lambda: w._script_timer.isActive())
    assert w.script_pause_btn.isVisible()
    assert not any(bar.isVisible() for bar in w.centralWidget().findChildren(QScrollBar))
    for widget in (w.script_pause_btn, w.fullscreen_button, w.cancel_btn, w.plot_canvas):
        assert w.rect().contains(widget.mapTo(w, widget.rect().topLeft()))
        assert w.rect().contains(widget.mapTo(w, widget.rect().bottomRight()))


def test_scan_error_stops_and_records_failure(gui):
    app, w = gui
    w._controller.run_single_scan.side_effect = RuntimeError('connection lost')
    w._start_script()
    pump(app, lambda: w._script_job is None and w._thread is None)
    assert w._controller.run_single_scan.call_count == 1
    manifest = json.loads((w._script_dir / 'manifest.json').read_text())
    assert not manifest['segments'][0]['ok']
    assert 'connection lost' in manifest['segments'][0]['error']


def test_pause_while_scanning_takes_effect_after_save(gui):
    from threading import Event
    app, w = gui
    gate = Event()
    raw = w._controller.run_single_scan.return_value
    def scan(settings):
        gate.wait(2)
        return raw
    w._controller.run_single_scan.side_effect = scan
    w._start_script()
    w._pause_script()
    gate.set()
    pump(app, lambda: w._script_timer.isActive())
    assert w._script_paused
    assert w._controller.run_single_scan.call_count == 1
    assert list(w._script_dir.glob('*.csv'))


def test_long_script_releases_old_arrays_but_keeps_manifest(gui):
    import weakref
    app, w = gui
    # Seed an obsolete saved scan and a reference whose sequence differs from its index.
    obsolete = w._session.add(w._controller.run_single_scan.return_value)
    obsolete.saved = True
    ref = w._session.add(w._controller.run_single_scan.return_value, is_reference=True)
    ref.saved = True
    for record in w._session.records:
        w.history_combo.addItem(f'#{record.sequence} test')
    old_array = weakref.ref(obsolete.raw.wavelengths)
    del obsolete
    text = w.script_editor.toPlainText().split('scan wide')[0]
    w.script_editor.setPlainText(text + '\n'.join(
        f'scan pass{i} 1500 1630 step=1pm speed=20' for i in range(24)))
    w._start_script()
    pump(app, lambda: w._script_job is None and w._thread is None, timeout=15)
    assert len(w._session.records) == w.history_combo.count() == 20
    assert old_array() is None
    assert w._session.reference is ref.raw
    assert w._session.reference_index == 0
    assert w.history_combo.itemText(0).startswith('#2 ')
    assert '#2' in w.reference_label.text()
    assert w._last_record.sequence == 26
    assert all(result.record is None for result in w._script_results)
    manifest = json.loads((w._script_dir / 'manifest.json').read_text())
    assert len(manifest['segments']) == 24
    assert all(s['reference_index'] == 1 and s['loss_available'] for s in manifest['segments'])
    w._clear_saved_history()
    assert len(w._session.records) == w.history_combo.count() == 2
    assert len(list(w._script_dir.glob('*.csv'))) == 24


def test_script_uses_exact_output_and_preserves_previous_run(gui, tmp_path):
    app, w = gui
    target = tmp_path / 'new' / 'measurements'
    w.script_editor.setPlainText(f'job two_pass\ndevice chip\noutput "{target}"\n'
                                'scan wide 1500 1630 step=1pm speed=20')
    w._start_script()
    pump(app, lambda: w._script_job is None and w._thread is None)
    assert w._script_dir == target
    assert target.is_dir()
    csv_path = next(target.glob('*.csv'))
    original = csv_path.read_bytes()
    original_manifest = (target / 'manifest.json').read_bytes()
    w._start_script()
    pump(app, lambda: w._script_job is None and w._thread is None)
    assert w._script_dir == target
    assert len(list(target.glob('*.csv'))) == 2
    assert not any(p.is_dir() for p in target.iterdir())
    assert csv_path.read_bytes() == original
    assert (target / 'manifest.json').read_bytes() == original_manifest
    manifest = json.loads((target / 'manifest_001.json').read_text())
    assert manifest['segments'][0]['csv'] != csv_path.name
    assert (target / manifest['segments'][0]['csv']).exists()
