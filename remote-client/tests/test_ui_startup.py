"""Headless UI lifecycle test with no network or real instruments."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import Mock

from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest

from santecpro import ui_app


def test_window_initializes_in_background_and_keeps_output_on(monkeypatch):
    app = QApplication.instance() or QApplication([])
    remote = Mock()
    remote.check_instruments.return_value = {'tsl_idn': 'TSL', 'mpm_idn': 'MPM'}
    remote.prepare_laser.side_effect = lambda **kw: kw['progress']('预热完成')
    monkeypatch.setattr('santecpro.ui_controller.RemoteScanner', Mock(return_value=remote))
    window = ui_app.ScanMainWindow()
    try:
        for _ in range(200):
            app.processEvents()
            if window._controller.is_connected and window._thread is None:
                break
            QTest.qWait(5)
        assert window._thread is None
        assert window.scan_btn.isEnabled()
        assert not window.cancel_btn.isEnabled()
        remote.prepare_laser.assert_called_once()
        remote.check_instruments.assert_called_once()
        window._controller.laser_off()
        window._set_busy(False)
        assert not window.scan_btn.isEnabled()
        assert window.laser_on_btn.isEnabled()
        remote.laser_off.reset_mock()
        window.close()
        remote.laser_off.assert_not_called()
    finally:
        if window._thread is not None:
            window._thread.quit()
            window._thread.wait(2000)
        window.close()
