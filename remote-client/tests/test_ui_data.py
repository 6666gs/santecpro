import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import csv
import numpy as np
from PyQt5.QtWidgets import QApplication

from santecpro import ui_app
from santecpro.results import ScanResult


def result(power):
    return ScanResult(np.array([1550,1551.]), np.array([power,power]), np.array([7.,7.]),
                      scan_params={'start_wl':1550,'stop_wl':1551,'step':1},
                      timestamp='2026-09-16T12:00:00')


def test_ui_keeps_both_formats_and_reference_export_is_raw(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui_app.QTimer, 'singleShot', lambda *args: None)
    window = ui_app.ScanMainWindow()
    try:
        window.save_check.setChecked(False)
        window._task_finished(ui_app.WorkerResult('reference_scan', result(-2)))
        assert window._last_record.is_reference
        assert not window.export_combo.model().item(1).isEnabled()
        window._task_finished(ui_app.WorkerResult('scan', result(-12)))
        record = window._last_record
        assert window.export_combo.model().item(1).isEnabled()
        assert len(window._session.records) == 2
        np.testing.assert_allclose(record.loss[1], 10)
        window.save_path_edit.setText(str(tmp_path / 'device.csv'))
        window.export_combo.setCurrentIndex(0)
        window._save_last_result()
        window.export_combo.setCurrentIndex(1)
        window._save_last_result()
        assert (tmp_path / 'device_raw.csv').exists()
        assert (tmp_path / 'device_loss.csv').exists()
        assert window._last_record is record
        # Selection and view switches must not recalculate or delete losses.
        window.view_combo.setCurrentIndex(1)
        window._clear_reference()
        np.testing.assert_allclose(record.loss[1], 10)
        window.history_combo.setCurrentIndex(0)
        assert window.export_combo.currentData() == 'raw'
        window._save_last_result()
        assert (tmp_path / 'device_001_raw.csv').exists()
        rows=list(csv.reader((tmp_path / 'device_001_raw.csv').open()))
        assert rows[14][2] == 'Raw_M1-Ch1-R1(dBm)'
        assert window._last_record.is_reference
    finally:
        window.close()
