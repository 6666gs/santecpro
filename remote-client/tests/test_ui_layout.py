"""Bounded, scroll-free layout checks, including large history labels."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QApplication, QScrollArea, QScrollBar
from santecpro.ui_app import ScanMainWindow


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    window = ScanMainWindow(auto_connect=False)
    yield app, window
    window.close()


@pytest.mark.parametrize('width,height', [(900,560),(1024,640),(1280,800),(1440,900),(1728,1117)])
def test_controls_fit_without_scrollbars(window, width, height):
    app, w = window
    w.resize(width, height)
    w.show()
    for check in w.channel_checks:
        check.setChecked(True)
    w.history_combo.addItem('测量 ' + 'long history description ' * 30)
    w.status_label.setText('采集完成：' + 'CH1 CH2 CH3 CH4 / Reference information ' * 10)
    app.processEvents()
    assert w.width() == width and w.height() == height
    assert not w.findChildren(QScrollArea)
    assert not [bar for bar in w.findChildren(QScrollBar) if bar.isVisible()]
    for control in [w.start_spin, w.stop_spin, w.step_combo, w.speed_combo,
                    w.power_spin, w.channel_button, w.scan_btn, w.cancel_btn,
                    w.reference_scan_btn, w.save_btn, w.save_check, w.export_combo,
                    w.view_combo, w.history_combo, w.fullscreen_button, w.settings_button]:
        assert control.isVisible()
        rect = control.rect()
        rect.moveTopLeft(control.mapTo(w.centralWidget(), QPoint(0,0)))
        assert w.centralWidget().rect().contains(rect), (control, rect)
        assert control.width() >= 50
    assert w.plot_canvas.height() >= 200


def test_settings_pages_are_bounded_and_all_controls_accessible(window):
    app, w = window
    w.resize(900,560)
    w.show()
    w.settings_menu.popup(w.settings_button.mapToGlobal(QPoint(0, w.settings_button.height())))
    app.processEvents()
    try:
        for tab in range(w.settings_tabs.count()):
            w.settings_tabs.setCurrentIndex(tab)
            app.processEvents()
            page = w.settings_tabs.currentWidget()
            assert page.width() >= 400
            assert w.settings_menu.height() < 500
            assert not [bar for bar in page.findChildren(QScrollBar) if bar.isVisible()]
        w.settings_tabs.setCurrentIndex(0)
        assert w.server_url_edit.isVisible()
        w.settings_tabs.setCurrentIndex(1)
        assert w.range_combo.isVisible() and w.module_spin.isVisible()
        w.settings_tabs.setCurrentIndex(2)
        assert w.save_path_edit.isVisible()
    finally:
        w.settings_menu.hide()


def test_fullscreen_roundtrip_and_busy_cancellation(window):
    app, w = window
    w.show()
    w._toggle_fullscreen()
    app.processEvents()
    assert w.isFullScreen()
    assert w.fullscreen_button.text() == '退出全屏'
    w._exit_fullscreen()
    app.processEvents()
    assert not w.isFullScreen()
    w._task_label = 'scan'
    w._set_busy(True)
    assert w.cancel_btn.isEnabled()
    assert not w.scan_btn.isEnabled()
    assert not w.laser_off_btn.isEnabled()
