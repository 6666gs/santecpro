import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication
from matplotlib.backend_bases import MouseEvent
from santecpro.ui_app import PlotCanvas
from santecpro.results import ScanResult
from santecpro.session import ScanRecord


@pytest.fixture
def canvas():
    app = QApplication.instance() or QApplication([])
    c = PlotCanvas()
    yield c
    c.close()


def raw():
    return ScanResult(np.array([1500., 1501., 1502., 1503.]),
                      np.array([-100., -5., -4., 100.]), np.zeros(4),
                      channel_powers={1: np.array([-100., -5., -4., 100.]),
                                      2: np.array([-90., -10., -8., 90.])})


def test_x_zoom_y_fits_all_channels_and_full_reset(canvas):
    scan = raw()
    canvas.plot_scan(scan)
    original = (canvas.axes.get_xlim(), canvas.axes.get_ylim())
    canvas.zoom_x(1502, 1501)
    assert canvas.axes.get_xlim() == (1501, 1502)
    assert canvas.axes.get_ylim() == pytest.approx((-10.3, -3.7))
    np.testing.assert_array_equal(scan.powers, [-100, -5, -4, 100])
    canvas.show_all()
    assert (canvas.axes.get_xlim(), canvas.axes.get_ylim()) == original


def test_drag_events_zoom_and_remain_usable_after_replot(canvas):
    canvas.resize(800, 500)
    for plot in (lambda: canvas.plot_scan(raw()), lambda: canvas.plot_reference(raw()),
                 lambda: canvas.plot_loss(ScanRecord(raw(), loss={1: np.array([90., 2., 3., 80.])}))):
        plot()
        canvas.set_x_zoom_enabled(True)
        canvas.draw()
        y = np.mean(canvas.axes.get_ylim())
        for name, x in [('button_press_event',1501), ('motion_notify_event',1502), ('button_release_event',1502)]:
            px, py = canvas.axes.transData.transform((x,y))
            event = MouseEvent(name, canvas, px, py, button=1)
            canvas.callbacks.process(name, event)
        assert canvas.axes.get_xlim() == pytest.approx((1501,1502), abs=.01)
        assert canvas.axes.get_ylim()[1] < 5
        canvas.show_all()
        assert canvas.axes.get_xlim()[0] < 1501


def test_flat_data_tiny_selection_and_switch_history(canvas):
    scan = raw()
    scan.channel_powers = {1: np.ones(4)}
    canvas.plot_scan(scan)
    canvas.zoom_x(1501.2, 1501.3)  # no sampled points inside, but line still visible
    assert canvas.axes.get_ylim() == pytest.approx((.999,1.001))
    canvas.plot_scan(raw())
    assert canvas.axes.get_xlim()[0] < 1501
    old = canvas.axes.get_xlim()
    canvas.zoom_x(float('nan'), 1502)
    canvas.zoom_x(1501,1501)
    assert canvas.axes.get_xlim() == old


def test_empty_plot_controls_are_safe(canvas):
    canvas.set_x_zoom_enabled(True)
    canvas.zoom_x(.2,.5)
    canvas.show_all()
    assert canvas.axes.get_xlim() == (0,1)
