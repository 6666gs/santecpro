"""PyQt5 desktop UI for Santec TSL/MPM scanning."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

_CACHE_DIR = os.path.join(tempfile.gettempdir(), "santecpro-cache")
os.makedirs(_CACHE_DIR, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", os.path.join(_CACHE_DIR, "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", _CACHE_DIR)

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
from PyQt5.QtCore import QObject, QThread, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QAction,
    QMenu,
    QToolButton,
    QWidgetAction,
    QTabWidget,
    QSizePolicy,
    QShortcut,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from santecpro.results import ScanResult
from santecpro.sweep_rules import ALLOWED_STEP_PM, get_allowed_speeds_nm_s
import config
from santecpro.ui_controller import ConnectionSettings, ScanSettings, ScanUiController

from santecpro.session import ScanSession, ScanRecord
from santecpro.exporter import save_record_csv
from santecpro.ui_script import ScriptUiMixin


@dataclass
class WorkerResult:
    label: str
    value: object | None = None


class TaskWorker(QObject):
    """Run a blocking controller task in a Qt worker thread."""

    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, label: str, task: Callable[[], object | None]) -> None:
        super().__init__()
        self._label = label
        self._task = task

    def run(self) -> None:
        try:
            value = self._task()
            self.finished.emit(WorkerResult(self._label, value))
        except Exception:
            self.failed.emit(traceback.format_exc())


class PlotCanvas(FigureCanvas):
    """Matplotlib canvas embedded in the PyQt UI."""

    def __init__(self) -> None:
        self.figure = Figure(figsize=(7, 4), tight_layout=True)
        self.axes = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self._selector = None
        self._zoom_enabled = False
        self.clear()

    def clear(self) -> None:
        self.axes.clear()
        self.axes.ticklabel_format(axis="x", style="plain", useOffset=False)
        self.axes.set_xlabel("Wavelength (nm)")
        self.axes.set_ylabel("Power (dBm)")
        self.axes.grid(True, alpha=0.3)
        self._reset_view()

    def plot_scan(self, result: ScanResult) -> None:
        self.axes.clear()
        for channel in result.channels():
            self.axes.plot(
                result.wavelengths,
                result.powers_for_channel(channel),
                linewidth=1.0,
                label=f"CH{channel} raw",
            )
        self.axes.ticklabel_format(axis="x", style="plain", useOffset=False)
        self.axes.set_xlabel("Wavelength (nm)")
        self.axes.set_ylabel("Power (dBm)")
        self.axes.grid(True, alpha=0.3)
        self.axes.set_title(f"Range {result.mpm_range}, {len(result.powers)} points")
        self.axes.legend(loc="best")
        self._reset_view()

    def plot_loss(self, record: ScanRecord) -> None:
        self.axes.clear()
        for channel, values in sorted(record.loss.items()):
            self.axes.plot(record.raw.wavelengths, values, linewidth=1.0, label=f"CH{channel} loss")
        self.axes.ticklabel_format(axis="x", style="plain", useOffset=False)
        self.axes.set_xlabel("Wavelength (nm)")
        self.axes.set_ylabel("Insertion loss (dB), reference − measurement")
        self.axes.grid(True, alpha=0.3)
        self.axes.legend(loc="best")
        self._reset_view()

    def plot_reference(self, reference: ScanResult) -> None:
        self.axes.clear()
        for channel in reference.channels():
            self.axes.plot(
                reference.wavelengths,
                reference.powers_for_channel(channel),
                linewidth=1.0,
                label=f"CH{channel} reference",
            )
        self.axes.ticklabel_format(axis="x", style="plain", useOffset=False)
        self.axes.set_xlabel("Wavelength (nm)")
        self.axes.set_ylabel("Reference power (dBm)")
        self.axes.grid(True, alpha=0.3)
        self.axes.set_title(f"Reference, {len(reference.powers)} points")
        self.axes.legend(loc="best")
        self._reset_view()


    def _reset_view(self) -> None:
        # Axes.clear removes the selector artist; replace its event handlers too.
        if self._selector is not None:
            self._selector.disconnect_events()
        self._full_limits = (self.axes.get_xlim(), self.axes.get_ylim())
        self._selector = SpanSelector(
            self.axes, self.zoom_x, "horizontal", button=1, useblit=False,
            props={"facecolor": "#3b82f6", "alpha": 0.2},
        )
        self._selector.set_active(self._zoom_enabled)
        self.draw_idle()

    def set_x_zoom_enabled(self, enabled: bool) -> None:
        self._zoom_enabled = enabled
        self._selector.set_active(enabled)
        self.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)
        if not enabled:
            self._selector.clear()

    def zoom_x(self, left: float, right: float) -> None:
        if not np.isfinite([left, right]).all():
            return
        left, right = sorted((left, right))
        full_left, full_right = sorted(self._full_limits[0])
        left, right = max(left, full_left), min(right, full_right)
        if right <= left:
            return
        visible = []
        for line in self.axes.lines:
            if not line.get_visible():
                continue
            x, y = np.asarray(line.get_xdata()), np.asarray(line.get_ydata())
            valid = np.isfinite(x) & np.isfinite(y)
            x, y = x[valid], y[valid]
            if not len(x):
                continue
            if x[0] > x[-1]:
                x, y = x[::-1], y[::-1]
            lo, hi = max(left, x[0]), min(right, x[-1])
            if hi < lo:
                continue
            visible.extend(y[(x >= lo) & (x <= hi)])
            # Include line values at the drag boundaries even between samples.
            visible.extend(np.interp([lo, hi], x, y))
        if not visible:
            return
        ymin, ymax = min(visible), max(visible)
        pad = max((ymax - ymin) * .05, .001)
        self.axes.set_xlim(left, right)
        self.axes.set_ylim(ymin - pad, ymax + pad)
        self.draw_idle()

    def show_all(self) -> None:
        self.axes.set_xlim(*self._full_limits[0])
        self.axes.set_ylim(*self._full_limits[1])
        self._selector.clear()
        self.draw_idle()


class AlignmentDialog(QDialog):
    """Editable fixed-wavelength output with automatic MPM readout range."""

    def __init__(
        self,
        controller: ScanUiController,
        power: float,
        mpm_module: int,
        mpm_channels: tuple[int, ...],
        mpm_range: int,
        parent: QWidget | None = None,
        *, wavelength: float = 1550.0,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("对光监视")
        self.resize(580, 300)
        self.setModal(True)
        self._thread = None
        self._monitoring = False
        self._closing = False
        self._apply_pending = False
        self._last_read_at = None
        self._refresh_ms = 100
        self._controller = controller
        self._module = mpm_module
        self._channels = mpm_channels
        self._labels: dict[int, QLabel] = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self._refresh_ms)
        self._timer.timeout.connect(self._poll)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.wavelength_spin = QDoubleSpinBox()
        self.wavelength_spin.setRange(1000, 2000)
        self.wavelength_spin.setDecimals(4)
        self.wavelength_spin.setSuffix(" nm")
        self.wavelength_spin.setValue(wavelength)
        self.power_spin = QDoubleSpinBox()
        self.power_spin.setRange(-30, 20)
        self.power_spin.setDecimals(2)
        self.power_spin.setSuffix(" dBm")
        self.power_spin.setValue(power)
        form.addRow("激光波长", self.wavelength_spin)
        form.addRow("出射功率", self.power_spin)
        layout.addLayout(form)
        layout.addWidget(QLabel(f"Module {mpm_module + 1} · MPM 自动量程；修改后点击应用"))
        self.state_label = QLabel("尚未开始；停止监视和关闭窗口均保持激光开启")
        layout.addWidget(self.state_label)
        row = QHBoxLayout()
        for channel in mpm_channels:
            label = QLabel(f"CH{channel}\n-- dBm")
            label.setMinimumWidth(95)
            label.setStyleSheet(
                "QLabel { background: #111827; color: #f9fafb; padding: 12px; "
                "border-radius: 6px; font-size: 16px; font-weight: 600; }"
            )
            label.setAlignment(QtAlignmentCenter())
            self._labels[channel] = label
            row.addWidget(label)
        layout.addLayout(row)
        buttons = QHBoxLayout()
        self.start_btn = QPushButton("应用并开始监视")
        self.stop_btn = QPushButton("停止")
        self.close_btn = QPushButton("关闭")
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        self.close_btn.clicked.connect(self.close)
        buttons.addWidget(self.start_btn)
        buttons.addWidget(self.stop_btn)
        buttons.addWidget(self.close_btn)
        layout.addLayout(buttons)

    def _start(self) -> None:
        if self._thread is not None:
            self._apply_pending = True
            self.state_label.setText("当前读取结束后应用新参数…")
            return
        self._apply_pending = False
        self._last_read_at = None
        self._timer.stop()
        self._monitoring = True
        power, wavelength = self.power_spin.value(), self.wavelength_spin.value()
        for label in self._labels.values():
            label.setText("设置中…")
        self.state_label.setText(f"正在应用 {wavelength:.4f} nm / {power:.2f} dBm")
        self._launch(lambda: self._controller.start_alignment(
            power, self._module, self._channels, wavelength=wavelength))

    def _launch(self, task) -> None:
        self._request_started = time.monotonic()
        self._thread = QThread(self)
        self._worker = TaskWorker("alignment", task)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._received)
        self._worker.failed.connect(self._failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._finished)
        self._thread.start()

    def _received(self, result) -> None:
        self._set_powers(result.value)
        now = time.monotonic()
        rate = ""
        if self._last_read_at is not None:
            interval = now - self._last_read_at
            rate = f" · 实际 {1 / max(interval, .001):.1f} 次/秒"
        self._last_read_at = now
        if self._monitoring:
            self.state_label.setText("监视中 · 自动量程" + rate + "；修改后点击应用")

    def _failed(self, trace: str) -> None:
        self._stop()
        self.state_label.setText("监视失败：" + trace.splitlines()[-1])
        for label in self._labels.values():
            label.setText("读取失败")

    def _finished(self) -> None:
        self._thread = None
        self._worker = None
        self.start_btn.setEnabled(True)
        if self._closing:
            self.close()
        elif self._apply_pending:
            self._start()
        elif self._monitoring:
            elapsed_ms = (time.monotonic() - self._request_started) * 1000
            self._timer.start(max(1, int(self._refresh_ms - elapsed_ms)))

    def _stop(self) -> None:
        self._monitoring = False
        self._apply_pending = False
        self._timer.stop()
        self.state_label.setText("已停止监视；激光保持当前设置")

    def _poll(self) -> None:
        if self._thread is None and self._monitoring:
            self._timer.stop()
            self._launch(lambda: self._controller.read_alignment_powers(self._module, self._channels))

    def reject(self) -> None:
        self._stop()
        if self._thread is not None:
            self._closing = True
            self.start_btn.setEnabled(False)
            self.state_label.setText("等待当前仪器请求结束后关闭…")
            return
        super().reject()

    def _set_powers(self, powers: dict[int, float]) -> None:
        for channel, label in self._labels.items():
            power = powers.get(channel)
            text = "--" if power is None else f"{power:.3f}"
            label.setText(f"CH{channel}\n{text} dBm")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._stop()
        if self._thread is not None:
            self._closing = True
            self.start_btn.setEnabled(False)
            self.state_label.setText("等待当前仪器请求结束后关闭…")
            event.ignore()
            return
        super().closeEvent(event)


def QtAlignmentCenter():
    from PyQt5.QtCore import Qt

    return Qt.AlignCenter


class ScanMainWindow(ScriptUiMixin, QMainWindow):
    """Main PyQt window for Santec scanning."""

    def __init__(self, *, auto_connect: bool = True) -> None:
        super().__init__()
        self.setWindowTitle("SantecPro 扫谱控制")
        self.resize(1280, 800)
        self.setMinimumSize(900, 560)
        self._preview = False

        self._controller = ScanUiController()
        self._last_result: ScanResult | None = None
        self._session = ScanSession()
        self._last_record: ScanRecord | None = None
        self._thread: QThread | None = None
        self._worker: TaskWorker | None = None
        self._cancel_thread: QThread | None = None
        self._cancel_worker: TaskWorker | None = None
        self._task_label = ""

        root = QWidget()
        self.setCentralWidget(root)

        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(18, 12, 18, 12)
        main_layout.setSpacing(10)
        self._build_controls()
        self._init_script()
        main_layout.addWidget(self._build_header())
        main_layout.addWidget(self._build_parameters())
        main_layout.addWidget(self._build_output(), 1)
        main_layout.addWidget(self._build_actions())
        main_layout.addWidget(self.status_label)
        self._set_busy(False)
        self._refresh_record_controls()
        self.fullscreen_shortcut = QShortcut(QKeySequence("Ctrl+Meta+F" if sys.platform == "darwin" else "F11"), self)
        self.fullscreen_shortcut.activated.connect(self._toggle_fullscreen)
        self.escape_shortcut = QShortcut(QKeySequence("Escape"), self)
        self.escape_shortcut.activated.connect(self._exit_fullscreen)
        if auto_connect:
            QTimer.singleShot(0, self._connect)

    @staticmethod
    def _menu_button(text: str, menu: QMenu) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setMenu(menu)
        button.setPopupMode(QToolButton.InstantPopup)
        button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        button.setMinimumHeight(30)
        button.setStyleSheet("QToolButton { padding: 3px 16px 3px 8px; }")
        return button

    @staticmethod
    def _action(menu: QMenu, text: str, callback) -> QAction:
        action = menu.addAction(text)
        action.triggered.connect(callback)
        return action

    def _build_controls(self) -> None:
        # Widgets retain their identities; less-used options live in a bounded popup.
        self.server_url_edit = QLineEdit(config.SERVER_URL)
        self.tsl_addr_edit = QLineEdit(config.TSL_ADDRESS)
        self.mpm_addr_edit = QLineEdit(config.MPM_ADDRESS)
        self.connect_btn = QPushButton("连接 / 初始化")
        self.disconnect_btn = QPushButton("断开连接")
        self.start_server_btn = QPushButton("启动 Windows 服务")
        self.connect_btn.clicked.connect(self._connect)
        self.disconnect_btn.clicked.connect(self._disconnect)
        self.start_server_btn.clicked.connect(self._start_remote_server)
        self.start_spin = self._double_spin(1200, 1700, 1550, 4, .01)
        self.stop_spin = self._double_spin(1200, 1700, 1550.1, 4, .01)
        self.power_spin = self._double_spin(-20, 20, 0, 2, .5)
        self.step_combo = QComboBox()
        for step in ALLOWED_STEP_PM:
            self.step_combo.addItem(f"{step:g} pm", step / 1000)
        self.step_combo.setCurrentIndex(list(ALLOWED_STEP_PM).index(10))
        self.speed_combo = QComboBox()
        self.step_combo.currentIndexChanged.connect(self._update_speed_choices)
        self._update_speed_choices()
        self.range_combo = QComboBox()
        for value, text in [(1, "−30 ~ +10 dBm"), (2, "−40 ~ 0 dBm"), (3, "−50 ~ −10 dBm"),
                            (4, "−60 ~ −20 dBm"), (5, "−80 ~ −30 dBm")]:
            self.range_combo.addItem(f"Range {value} · {text}", value)
        self.module_spin = self._int_spin(0, 4, 0)
        self.sweep_mode_combo = QComboBox()
        self.sweep_mode_combo.addItem("1 - Continuous One-way")
        self.channel_checks = []
        channel_menu = QMenu(self)
        channel_panel = QWidget()
        channel_layout = QVBoxLayout(channel_panel)
        channel_layout.addWidget(QLabel("选择采集通道（可多选）"))
        for channel in range(1, 5):
            check = QCheckBox(f"CH{channel}")
            check.setChecked(channel == 1)
            check.toggled.connect(self._update_channel_label)
            self.channel_checks.append(check)
            channel_layout.addWidget(check)
        channel_action = QWidgetAction(channel_menu)
        channel_action.setDefaultWidget(channel_panel)
        channel_menu.addAction(channel_action)
        self.channel_button = self._menu_button("CH1", channel_menu)
        self.save_check = QCheckBox("自动保存")
        self.save_check.setChecked(True)
        self.save_path_edit = QLineEdit(str(Path.cwd() / "scan_result_raw.csv"))
        self.save_path_edit.setMinimumWidth(0)
        self.export_combo = QComboBox()
        self.export_combo.addItem("保存 Raw", "raw")
        self.export_combo.addItem("保存 Loss", "loss")
        self.export_combo.setToolTip("Loss = reference − measurement（正值插损）；只选择导出内容，不删除内存数据")
        self.view_combo = QComboBox()
        self.view_combo.addItem("显示 Raw", "raw")
        self.view_combo.addItem("显示 Loss", "loss")
        self.view_combo.currentIndexChanged.connect(self._plot_selected_record)
        self.history_combo = QComboBox()
        self.history_combo.setMinimumWidth(150)
        self.history_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.history_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.history_combo.setMinimumContentsLength(12)
        self.history_combo.setMaxVisibleItems(12)
        self.history_combo.currentIndexChanged.connect(self._select_history)
        self.reference_label = QLabel("未设置 reference：请先扫描线路")
        self.reference_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.reference_label.setMinimumWidth(0)
        self.scan_btn = QPushButton("扫描器件")
        self.scan_btn.setDefault(True)
        self.scan_btn.clicked.connect(self._run_scan)
        self.cancel_btn = QPushButton("取消扫描")
        self.cancel_btn.setToolTip("停止扫波与采集，保持激光开启")
        self.cancel_btn.clicked.connect(self._cancel_scan)
        self.reference_scan_btn = QPushButton("扫描 Reference")
        self.reference_scan_btn.clicked.connect(self._run_reference_scan)
        self.save_btn = QPushButton("保存所选扫描")
        self.save_btn.clicked.connect(self._save_last_result)
        self.reference_menu = QMenu(self)
        self.set_reference_btn = self._action(self.reference_menu, "将所选扫描设为 Reference", self._set_reference)
        self.view_reference_btn = self._action(self.reference_menu, "查看 Reference", self._view_reference)
        self.save_reference_btn = self._action(self.reference_menu, "保存 Reference Raw…", self._save_reference)
        self.reference_menu.addSeparator()
        self.clear_reference_btn = self._action(self.reference_menu, "清除当前 Reference", self._clear_reference)
        self.reference_menu.addSeparator()
        self._action(self.reference_menu, "清理已保存历史（保留当前结果和 Reference）", self._clear_saved_history)
        self.instrument_menu = QMenu(self)
        self.laser_on_btn = self._action(self.instrument_menu, "开启激光 / 等待预热", self._start_laser)
        self.laser_off_btn = self._action(self.instrument_menu, "手动关闭激光", lambda: self._run_task("laser_off", self._controller.laser_off))
        self.instrument_menu.addSeparator()
        self.alignment_btn = self._action(self.instrument_menu, "对光监视…", self._open_alignment_dialog)
        self.status_label = QLabel("未连接")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(32)
        self.status_label.setMaximumHeight(44)
        self.status_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._build_settings_menu()
        self._build_log_dialog()

    def _start_laser(self) -> None:
        self._run_task("laser_on", lambda: self._controller.laser_on(progress=self._worker.progress.emit))

    def _build_header(self) -> QWidget:
        panel = QWidget()
        row = QHBoxLayout(panel)
        row.setContentsMargins(0, 0, 0, 0)
        title = QLabel("SantecPro")
        font = title.font()
        font.setPointSize(18)
        font.setBold(True)
        title.setFont(font)
        row.addWidget(title)
        row.addStretch()
        self.instrument_button = self._menu_button("仪器", self.instrument_menu)
        self.settings_button = self._menu_button("设置", self.settings_menu)
        self.script_button = QPushButton("扫描脚本…")
        self.script_button.clicked.connect(self.script_dialog.show)
        self.script_pause_btn = QPushButton("暂停脚本")
        self.script_pause_btn.clicked.connect(self._pause_script)
        self.log_button = QPushButton("运行日志")
        self.log_button.clicked.connect(self.log_dialog.show)
        self.fullscreen_button = QPushButton("进入全屏")
        self.fullscreen_button.setToolTip("Mac：Control + Command + F；Esc 退出全屏")
        self.fullscreen_button.clicked.connect(self._toggle_fullscreen)
        for widget in (self.instrument_button, self.settings_button, self.script_button, self.script_pause_btn, self.log_button, self.fullscreen_button):
            row.addWidget(widget)
        return panel

    def _build_parameters(self) -> QWidget:
        panel = QGroupBox("扫描参数")
        grid = QGridLayout(panel)
        grid.setHorizontalSpacing(16)
        controls = [("起点 · nm", self.start_spin), ("终点 · nm", self.stop_spin),
                    ("步长", self.step_combo), ("速度 · nm/s", self.speed_combo),
                    ("光功率 · dBm", self.power_spin), ("通道", self.channel_button)]
        for col, (text, widget) in enumerate(controls):
            widget.setAccessibleName(text)
            widget.setMinimumWidth(0)
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            grid.addWidget(QLabel(text), 0, col)
            grid.addWidget(widget, 1, col)
            grid.setColumnStretch(col, 1)
        return panel

    def _build_output(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(QLabel("扫描历史"))
        row.addWidget(self.history_combo, 2)
        row.addWidget(self.view_combo)
        self.reference_button = self._menu_button("Reference", self.reference_menu)
        row.addWidget(self.reference_button)
        layout.addLayout(row)
        self.plot_canvas = PlotCanvas()
        self.plot_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.plot_canvas.setMinimumSize(300, 200)
        self.x_zoom_button = QPushButton("X 轴缩放")
        self.x_zoom_button.setCheckable(True)
        self.x_zoom_button.setToolTip("启用后在图内横向拖选波长区间，纵轴自动适配；可连续放大")
        self.x_zoom_button.toggled.connect(self.plot_canvas.set_x_zoom_enabled)
        self.plot_reset_button = QPushButton("显示全部")
        self.plot_reset_button.setToolTip("恢复完整曲线范围")
        self.plot_reset_button.clicked.connect(self.plot_canvas.show_all)
        row.addWidget(self.x_zoom_button)
        row.addWidget(self.plot_reset_button)
        layout.addWidget(self.plot_canvas, 1)
        layout.addWidget(self.reference_label)
        return panel

    def _build_actions(self) -> QWidget:
        panel = QWidget()
        row = QHBoxLayout(panel)
        row.setContentsMargins(0, 0, 0, 0)
        for widget in (self.reference_scan_btn, self.scan_btn, self.cancel_btn):
            widget.setMinimumHeight(32)
            row.addWidget(widget)
        row.addStretch()
        row.addWidget(self.save_check)
        row.addWidget(self.export_combo)
        row.addWidget(self.save_btn)
        return panel

    def _build_settings_menu(self) -> None:
        self.settings_menu = QMenu(self)
        panel = QWidget()
        panel.setFixedWidth(480)
        layout = QVBoxLayout(panel)
        self.settings_tabs = QTabWidget()
        layout.addWidget(self.settings_tabs)
        connection = QWidget()
        form = QFormLayout(connection)
        form.addRow("Windows 服务", self.server_url_edit)
        form.addRow("TSL 地址", self.tsl_addr_edit)
        form.addRow("MPM 地址", self.mpm_addr_edit)
        buttons = QHBoxLayout()
        buttons.addWidget(self.connect_btn)
        buttons.addWidget(self.disconnect_btn)
        form.addRow(buttons)
        form.addRow(self.start_server_btn)
        self.settings_tabs.addTab(connection, "连接")
        acquisition = QWidget()
        form = QFormLayout(acquisition)
        form.addRow("功率计量程", self.range_combo)
        form.addRow("模块编号（从 0 开始）", self.module_spin)
        form.addRow("扫描模式", self.sweep_mode_combo)
        note = QLabel("起止波长决定扫描方向。更改模块或通道后，请确认 reference 对应相同光路。")
        note.setWordWrap(True)
        form.addRow(note)
        self.settings_tabs.addTab(acquisition, "采集")
        output = QWidget()
        form = QFormLayout(output)
        form.addRow("保存路径", self.save_path_edit)
        browse = QPushButton("选择保存路径…")
        browse.clicked.connect(self._choose_csv_path)
        form.addRow(browse)
        note = QLabel("Raw 与 Loss 分别导出；同名文件自动编号。Reference 只导出 Raw。")
        note.setWordWrap(True)
        form.addRow(note)
        self.settings_tabs.addTab(output, "保存")
        done = QPushButton("完成")
        done.clicked.connect(self.settings_menu.hide)
        layout.addWidget(done, 0, Qt.AlignRight)
        action = QWidgetAction(self.settings_menu)
        action.setDefaultWidget(panel)
        self.settings_menu.addAction(action)

    def _build_log_dialog(self) -> None:
        # Full logs remain available in a separate window; the main page never scrolls.
        self.log_dialog = QDialog(self)
        self.log_dialog.setWindowTitle("运行日志")
        self.log_dialog.resize(720, 400)
        layout = QVBoxLayout(self.log_dialog)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)
        close = QPushButton("关闭")
        close.clicked.connect(self.log_dialog.hide)
        layout.addWidget(close, 0, Qt.AlignRight)

    def _update_channel_label(self) -> None:
        if hasattr(self, "channel_button"):
            channels = [f"CH{i + 1}" for i, check in enumerate(self.channel_checks) if check.isChecked()]
            self.channel_button.setText(" + ".join(channels) if len(channels) <= 2 else f"{len(channels)} 个通道")
            self.channel_button.setToolTip(" + ".join(channels) or "请至少选择一个通道")

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self._exit_fullscreen()
        else:
            self._before_fullscreen_maximized = self.isMaximized()
            self.showFullScreen()

    def _exit_fullscreen(self) -> None:
        if self.isFullScreen():
            if getattr(self, "_before_fullscreen_maximized", False):
                self.showMaximized()
            else:
                self.showNormal()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if hasattr(self, "fullscreen_button"):
            self.fullscreen_button.setText("退出全屏" if self.isFullScreen() else "进入全屏")

    def _connect(self) -> None:
        settings = self._connection_settings()
        self._run_task("connect", lambda: self._controller.connect(settings, progress=self._worker.progress.emit))

    def _start_remote_server(self) -> None:
        settings = self._connection_settings()
        self._run_task("start_server", lambda: self._controller.start_remote_server(settings))

    def _disconnect(self) -> None:
        self._controller.disconnect()
        self.status_label.setText("已断开")
        self._log("Disconnected; laser output unchanged")
        self._set_busy(False)

    def _run_scan(self) -> None:
        settings = self._scan_settings()
        self._run_task("scan", lambda: self._controller.run_single_scan(settings))

    def _run_reference_scan(self) -> None:
        settings = self._scan_settings()
        self._run_task("reference_scan", lambda: self._controller.run_single_scan(settings))

    def _open_alignment_dialog(self) -> None:
        channels = self._selected_channels()
        dialog = AlignmentDialog(
            self._controller,
            self.power_spin.value(),
            self.module_spin.value(),
            channels,
            int(self.range_combo.currentData()),
            self,
            wavelength=self.start_spin.value(),
        )
        dialog.show()

    def _save_last_result(self) -> None:
        if self._last_record is None:
            QMessageBox.warning(self, "无数据", "当前没有可保存的扫描结果。")
            return
        self._save_result(self._last_record)

    def _save_result(self, record: ScanRecord) -> None:
        kind = "raw" if record.is_reference else self.export_combo.currentData()
        self._export_record(record, self.save_path_edit.text().strip() or "scan_result.csv", kind)

    def _export_record(self, record: ScanRecord, path: str, kind: str) -> None:
        target = Path(path)
        stem = target.stem
        for suffix in ("_raw", "_loss"):
            if stem.endswith(suffix):
                stem = stem[:-len(suffix)]
                break
        target = target.with_name(f"{stem}_{kind}.csv")
        index = 1
        while target.exists():
            target = target.with_name(f"{stem}_{index:03d}_{kind}.csv")
            index += 1
        try:
            save_record_csv(record, str(target), kind)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        record.saved = True
        self._trim_history()
        self._log(f"Saved {kind}: {target}")

    def _save_reference(self) -> None:
        if self._session.reference_index is None:
            QMessageBox.warning(self, "无 reference", "请先扫描并设置线路 reference。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存 Reference Raw", "reference_raw.csv", "CSV Files (*.csv)")
        if path:
            self._export_record(self._session.records[self._session.reference_index], path, "raw")

    def _clear_saved_history(self) -> None:
        self._trim_history(clear=True)

    def _trim_history(self, *, clear: bool = False) -> None:
        selected = self._last_record
        labels = {record.sequence: self.history_combo.itemText(i)
                  for i, record in enumerate(self._session.records)}
        removed = self._session.trim_saved(max_records=0 if clear else 20,
                                          max_bytes=0 if clear else 256 * 1024**2,
                                          keep=selected)
        if removed:
            self.history_combo.blockSignals(True)
            self.history_combo.clear()
            for record in self._session.records:
                self.history_combo.addItem(labels[record.sequence])
            index = next((i for i, record in enumerate(self._session.records) if record is selected), -1)
            self.history_combo.setCurrentIndex(index)
            self.history_combo.blockSignals(False)
            self._refresh_record_controls()
            self._log(f"已释放 {removed} 条已保存历史的内存；磁盘文件不受影响")
        size = self._session.array_bytes / 1024**2
        self.history_combo.setToolTip(
            f"内存历史：{len(self._session.records)} 条，数组约 {size:.1f} MiB。"
            "超过 20 条或 256 MiB 时清理最早已保存记录；保留当前结果、最新结果、Reference 和未保存记录。"
            "删除磁盘 CSV 不会同步删除内存历史。")
        if len(self._session.records) > 20 or size > 256:
            self._log("历史超过缓存目标：保留了未保存数据 / 当前结果 / Reference，请及时保存并清理。")

    def _select_history(self, index: int) -> None:
        if index < 0 or index >= len(self._session.records):
            return
        self._last_record = self._session.records[index]
        self._last_result = self._last_record.raw
        self._refresh_record_controls()
        self._plot_selected_record()

    def _refresh_record_controls(self) -> None:
        available = bool(self._last_record and self._last_record.loss and not self._last_record.is_reference)
        for combo in (self.export_combo, self.view_combo):
            combo.model().item(1).setEnabled(available)
            if not available:
                combo.setCurrentIndex(0)
        self.save_reference_btn.setEnabled(self._thread is None and self._session.reference is not None)
        if self._session.reference_index is None:
            self.reference_label.setText("未设置 reference：请先扫描线路")
        else:
            self.reference_label.setText(f"当前 Reference：扫描 #{self._session.records[self._session.reference_index].sequence}（只保存 Raw）")

    def _plot_selected_record(self, *args) -> None:
        record = self._last_record
        if record is None:
            return
        if self.view_combo.currentData() == "loss" and record.loss:
            self.plot_canvas.plot_loss(record)
        else:
            self.plot_canvas.plot_scan(record.raw)
        state = (f"Raw + Loss，基于 Reference #{record.reference_index + 1}"
                 if record.loss else f"Raw；{record.loss_error}")
        self.status_label.setText(f"扫描 #{record.sequence}：{len(record.raw.wavelengths)} 点；{state}")

    def _run_task(self, label: str, task: Callable[[], object | None]) -> None:
        if self._preview:
            self.status_label.setText("界面预览模式：不连接或操作真实仪器")
            return
        if self._thread is not None:
            QMessageBox.information(self, "正在运行", "已有任务正在运行。")
            return
        self.settings_menu.hide()
        self._task_label = label
        self._set_busy(True)
        self._log(f"Starting {label}...")
        self._thread = QThread(self)
        self._worker = TaskWorker(label, task)
        self._worker.moveToThread(self._thread)
        self._worker.progress.connect(self._report_progress)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._task_finished)
        self._worker.failed.connect(self._task_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._thread_finished)
        self._thread.start()

    def _report_progress(self, message: str) -> None:
        self.status_label.setText(message)

    def _cancel_scan(self) -> None:
        if self._script_job is not None:
            self._stop_script()
            if self._thread is None:
                return
        if self._cancel_thread is not None:
            return
        self.cancel_btn.setEnabled(False)
        self._cancel_thread = QThread(self)
        self._cancel_worker = TaskWorker("cancel", self._controller.cancel_scan)
        self._cancel_worker.moveToThread(self._cancel_thread)
        self._cancel_thread.started.connect(self._cancel_worker.run)
        self._cancel_worker.finished.connect(self._cancel_requested)
        self._cancel_worker.failed.connect(self._task_failed)
        self._cancel_worker.finished.connect(self._cancel_thread.quit)
        self._cancel_worker.failed.connect(self._cancel_thread.quit)
        self._cancel_worker.finished.connect(self._cancel_worker.deleteLater)
        self._cancel_worker.failed.connect(self._cancel_worker.deleteLater)
        self._cancel_thread.finished.connect(self._cancel_thread.deleteLater)
        self._cancel_thread.finished.connect(self._cancel_finished)
        self._cancel_thread.start()

    def _cancel_requested(self, result: WorkerResult) -> None:
        self._log(f"取消请求: {result.value}；等待扫描线程停止，激光保持开启。")

    def _cancel_finished(self) -> None:
        self._cancel_thread = None
        self._cancel_worker = None
        self._set_busy(self._thread is not None)

    def closeEvent(self, event) -> None:
        if self._script_job is not None or self._thread is not None or self._cancel_thread is not None:
            QMessageBox.information(self, "任务仍在运行", "请等待初始化完成，或取消扫描后再关闭。激光不会自动关闭。")
            event.ignore()
            return
        event.accept()

    def _task_finished(self, result: WorkerResult) -> None:
        self._log(f"Finished {result.label}")
        if result.label == "connect":
            self.status_label.setText(f"已连接，激光就绪：{result.value.get('tsl_idn', '')} / {result.value.get('mpm_idn', '')}")
        elif result.label == "laser_on":
            self.status_label.setText("激光已就绪")
        elif result.label == "laser_off":
            self.status_label.setText("激光已手动关闭；再次开启需等待预热")
        elif result.label == "start_server":
            self.status_label.setText(f"Windows 服务已启动: {result.value}")
        elif result.label == "script_scan" and isinstance(result.value, ScanResult):
            self._script_result(result.value)
        elif result.label in ("scan", "reference_scan") and isinstance(result.value, ScanResult):
            raw = result.value
            raw.scan_params.setdefault("tsl_idn", self._controller._tsl_idn)
            raw.scan_params.setdefault("mpm_idn", self._controller._mpm_idn)
            record = self._session.add(raw, is_reference=result.label == "reference_scan")
            index = len(self._session.records) - 1
            self.history_combo.addItem(f"#{record.sequence} {'Reference' if record.is_reference else '测量'} {raw.timestamp}")
            self.history_combo.setCurrentIndex(index)
            self._select_history(index)
            if record.loss_error and not record.is_reference:
                self._log(record.loss_error)
            if self.save_check.isChecked():
                self._save_result(record)
            self._trim_history()

    def _task_failed(self, trace: str) -> None:
        if self._script_job is not None:
            self._script_stopped = True
            self._script_error = trace.splitlines()[-1] if trace else "Unknown error"
        self._log(trace)
        QMessageBox.critical(self, "任务失败", trace.splitlines()[-1] if trace else "Unknown error")

    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._set_busy(False)
        if self._script_job is not None:
            self._script_after_thread()

    def _connection_settings(self) -> ConnectionSettings:
        return ConnectionSettings(
            server_url=self.server_url_edit.text().strip(),
            tsl_address=self.tsl_addr_edit.text().strip(),
            mpm_address=self.mpm_addr_edit.text().strip(),
        )

    def _scan_settings(self) -> ScanSettings:
        sweep_mode = int(self.sweep_mode_combo.currentText().split(" ", 1)[0])
        channels = self._selected_channels()
        return ScanSettings(
            start_wl=self.start_spin.value(),
            stop_wl=self.stop_spin.value(),
            step=float(self.step_combo.currentData()),
            speed=float(self.speed_combo.currentData()),
            power=self.power_spin.value(),
            sweep_mode=sweep_mode,
            mpm_range=int(self.range_combo.currentData()),
            mpm_module=self.module_spin.value(),
            mpm_channel=channels[0],
            mpm_averaging_time_ms=0.01,
            mpm_channels=channels,
        )

    def _selected_channels(self) -> tuple[int, ...]:
        channels = tuple(
            index + 1 for index, check in enumerate(self.channel_checks) if check.isChecked()
        )
        if not channels:
            QMessageBox.warning(self, "未选择通道", "至少需要选择一个 MPM 通道。")
            raise ValueError("at least one MPM channel must be selected")
        return channels

    def _set_reference(self) -> None:
        index = self.history_combo.currentIndex()
        if index < 0:
            QMessageBox.warning(self, "无数据", "请先扫描线路，再设置 reference。")
            return
        self._session.set_reference(index)
        record = self._session.records[index]
        self.history_combo.setItemText(index, f"#{record.sequence} Reference {self._last_record.raw.timestamp}")
        self._refresh_record_controls()
        self._plot_selected_record()
        self._log(f"Reference set from scan #{record.sequence}; future scans retain raw and loss")

    def _clear_reference(self) -> None:
        self._session.clear_reference()
        self._refresh_record_controls()
        self._log("Reference cleared; stored measurements unchanged")

    def _view_reference(self) -> None:
        if self._session.reference is None:
            QMessageBox.warning(self, "无 reference", "当前没有扫描设置的 reference。")
            return
        self.plot_canvas.plot_reference(self._session.reference)

    def _choose_csv_path(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存 CSV",
            self.save_path_edit.text().strip() or "scan_result_raw.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if path:
            self.save_path_edit.setText(path)

    def _update_speed_choices(self) -> None:
        step = float(self.step_combo.currentData())
        current = self.speed_combo.currentData()
        allowed = get_allowed_speeds_nm_s(step)
        self.speed_combo.clear()
        for speed in allowed:
            self.speed_combo.addItem(str(speed), float(speed))
        if current in allowed:
            self.speed_combo.setCurrentIndex(allowed.index(current))

    def _set_busy(self, busy: bool) -> None:
        script_active = self._script_job is not None
        busy = busy or script_active
        self.script_button.setEnabled(not busy)
        self.script_pause_btn.setVisible(script_active)
        self.script_pause_btn.setEnabled(script_active and not self._script_stopped)
        self.script_pause_btn.setText('继续脚本' if self._script_paused else '暂停脚本')
        for widget in [
            self.connect_btn,
            self.disconnect_btn,
            self.start_server_btn,
            self.laser_on_btn,
            self.laser_off_btn,
            self.alignment_btn,
            self.scan_btn,
            self.save_btn,
            self.set_reference_btn,
            self.clear_reference_btn,
            self.view_reference_btn,
            self.reference_scan_btn,
            self.save_reference_btn,
            self.history_combo,
        ]:
            widget.setEnabled(not busy)
        connected = self._controller.is_connected
        ready = connected and self._controller.laser_ready
        self.scan_btn.setEnabled(not busy and ready)
        self.reference_scan_btn.setEnabled(not busy and ready)
        self.save_reference_btn.setEnabled(not busy and self._session.reference is not None)
        self.alignment_btn.setEnabled(not busy and ready)
        self.laser_on_btn.setEnabled(not busy and connected)
        self.laser_off_btn.setEnabled(not busy and connected)
        self.history_combo.setEnabled(not busy or script_active)
        for control in (self.start_spin, self.stop_spin, self.step_combo, self.speed_combo,
                        self.power_spin, self.channel_button, self.save_check):
            control.setEnabled(not script_active)
        self.settings_button.setEnabled(not script_active)
        self.export_combo.setEnabled(not script_active)
        self.cancel_btn.setText("停止脚本" if script_active else "取消扫描")
        self.cancel_btn.setEnabled(busy and self._task_label in ("scan", "reference_scan", "script_scan") and self._cancel_thread is None)

    def _log(self, message: str) -> None:
        self.log_text.append(message)

    @staticmethod
    def _double_spin(
        minimum: float,
        maximum: float,
        value: float,
        decimals: int,
        step: float,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setValue(value)
        return spin

    @staticmethod
    def _int_spin(minimum: int, maximum: int, value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        return spin


def main() -> int:
    parser = argparse.ArgumentParser(description="SantecPro macOS/desktop scan UI")
    display = parser.add_mutually_exclusive_group()
    display.add_argument("--fullscreen", action="store_true", help="start in native full screen")
    display.add_argument("--windowed", action="store_true", help="start in a normal resizable window")
    parser.add_argument("--preview", action="store_true", help="show sample spectra without connecting to instruments")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    window = ScanMainWindow(auto_connect=not args.preview)
    if args.preview:
        window._preview = True
        window.setWindowTitle("SantecPro · 界面预览（未连接仪器）")
        window.save_check.setChecked(False)
        wavelengths = np.linspace(1550, 1550.1, 501)
        for label, powers in [
            ("reference_scan", np.full(501, -2.0)),
            ("scan", -8 - 14 / (1 + ((wavelengths - 1550.045) / .003) ** 2)),
        ]:
            scan = ScanResult(wavelengths, powers, np.full(501, 7.0),
                              scan_params={"start_wl":1550., "stop_wl":1550.1, "step":.0002},
                              timestamp="预览数据", channel_powers={1:powers})
            window._task_finished(WorkerResult(label, scan))
        window._set_busy(False)
        window.status_label.setText("界面预览 · 示例光谱 · 未连接仪器")
    if args.fullscreen:
        window.showFullScreen()
    elif args.windowed:
        window.show()
    else:
        window.showMaximized()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
