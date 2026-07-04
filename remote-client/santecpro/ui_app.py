"""PyQt5 desktop UI for Santec TSL/MPM scanning."""

from __future__ import annotations

import os
import sys
import tempfile
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
from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal
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
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from santecpro.reference import calculate_reference_il_for_channel
from santecpro.results import ScanResult
from santecpro.sweep_rules import ALLOWED_STEP_PM, get_allowed_speeds_nm_s
import config
from santecpro.ui_controller import ConnectionSettings, ScanSettings, ScanUiController


@dataclass
class WorkerResult:
    label: str
    value: object | None = None


class TaskWorker(QObject):
    """Run a blocking controller task in a Qt worker thread."""

    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

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
        self.clear()

    def clear(self) -> None:
        self.axes.clear()
        self.axes.set_xlabel("Wavelength (nm)")
        self.axes.set_ylabel("Power (dBm)")
        self.axes.grid(True, alpha=0.3)
        self.draw_idle()

    def plot_scan(self, result: ScanResult) -> None:
        self.axes.clear()
        for channel in result.channels():
            self.axes.plot(
                result.wavelengths,
                result.powers_for_channel(channel),
                linewidth=1.0,
                label=f"CH{channel} raw",
            )
        self.axes.set_xlabel("Wavelength (nm)")
        self.axes.set_ylabel("Power (dBm)")
        self.axes.grid(True, alpha=0.3)
        self.axes.set_title(f"Range {result.mpm_range}, {len(result.powers)} points")
        self.axes.legend(loc="best")
        self.draw_idle()

    def plot_reference_il(self, result: ScanResult, reference: ScanResult) -> None:
        self.axes.clear()
        for channel in result.channels():
            if channel in reference.channels():
                il = calculate_reference_il_for_channel(reference, result, channel)
                self.axes.plot(il.wavelengths, il.il, linewidth=1.0, label=f"CH{channel} IL")
            self.axes.plot(
                result.wavelengths,
                result.powers_for_channel(channel),
                linewidth=0.8,
                linestyle="--",
                alpha=0.45,
                label=f"CH{channel} raw",
            )
        self.axes.set_xlabel("Wavelength (nm)")
        self.axes.set_ylabel("Insertion loss (dB)")
        self.axes.grid(True, alpha=0.3)
        self.axes.set_title(f"IL/raw, {len(result.wavelengths)} points")
        self.axes.legend(loc="best")
        self.draw_idle()

    def plot_reference(self, reference: ScanResult) -> None:
        self.axes.clear()
        for channel in reference.channels():
            self.axes.plot(
                reference.wavelengths,
                reference.powers_for_channel(channel),
                linewidth=1.0,
                label=f"CH{channel} reference",
            )
        self.axes.set_xlabel("Wavelength (nm)")
        self.axes.set_ylabel("Reference power (dBm)")
        self.axes.grid(True, alpha=0.3)
        self.axes.set_title(f"Reference, {len(reference.powers)} points")
        self.axes.legend(loc="best")
        self.draw_idle()


class AlignmentDialog(QDialog):
    """Fixed-power MPM readout for grating-coupler alignment."""

    def __init__(
        self,
        controller: ScanUiController,
        power: float,
        mpm_module: int,
        mpm_channels: tuple[int, ...],
        mpm_range: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("对光监视")
        self.resize(520, 260)
        self._controller = controller
        self._power = power
        self._module = mpm_module
        self._channels = mpm_channels
        self._range = mpm_range
        self._labels: dict[int, QLabel] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(700)
        self._timer.timeout.connect(self._poll)

        layout = QVBoxLayout(self)
        top = QLabel(f"Power {power:.2f} dBm, Module {mpm_module}, Range {mpm_range}")
        layout.addWidget(top)
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
        self.start_btn = QPushButton("开始监视")
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
        try:
            powers = self._controller.start_alignment(
                self._power,
                self._module,
                self._channels,
                self._range,
            )
            self._set_powers(powers)
            self._timer.start()
        except Exception as exc:
            QMessageBox.critical(self, "对光启动失败", str(exc))

    def _stop(self) -> None:
        self._timer.stop()

    def _poll(self) -> None:
        try:
            powers = self._controller.read_alignment_powers(self._module, self._channels)
            self._set_powers(powers)
        except Exception as exc:
            self._timer.stop()
            QMessageBox.critical(self, "读取失败", str(exc))

    def _set_powers(self, powers: dict[int, float]) -> None:
        for channel, label in self._labels.items():
            power = powers.get(channel)
            text = "--" if power is None else f"{power:.3f}"
            label.setText(f"CH{channel}\n{text} dBm")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._timer.stop()
        super().closeEvent(event)


def QtAlignmentCenter():
    from PyQt5.QtCore import Qt

    return Qt.AlignCenter


class ScanMainWindow(QMainWindow):
    """Main PyQt window for Santec scanning."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SantecPro 扫谱控制")
        self.resize(1180, 760)

        self._controller = ScanUiController()
        self._last_result: ScanResult | None = None
        self._reference_result: ScanResult | None = None
        self._thread: QThread | None = None
        self._worker: TaskWorker | None = None

        root = QWidget()
        self.setCentralWidget(root)

        main_layout = QHBoxLayout(root)
        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setMinimumWidth(380)
        controls_scroll.setWidget(self._build_controls())
        main_layout.addWidget(controls_scroll, 0)
        main_layout.addWidget(self._build_output(), 1)

    def _build_controls(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        conn_box = QGroupBox("连接")
        conn_form = QFormLayout(conn_box)
        self.server_url_edit = QLineEdit(config.SERVER_URL)
        self.tsl_addr_edit = QLineEdit(config.TSL_ADDRESS)
        self.mpm_addr_edit = QLineEdit(config.MPM_ADDRESS)
        conn_form.addRow("Server URL", self.server_url_edit)
        conn_form.addRow("TSL 地址", self.tsl_addr_edit)
        conn_form.addRow("MPM 地址", self.mpm_addr_edit)

        conn_buttons = QHBoxLayout()
        self.connect_btn = QPushButton("连接")
        self.disconnect_btn = QPushButton("断开")
        self.start_server_btn = QPushButton("启动 Windows 服务")
        self.connect_btn.clicked.connect(self._connect)
        self.disconnect_btn.clicked.connect(self._disconnect)
        self.start_server_btn.clicked.connect(self._start_remote_server)
        conn_buttons.addWidget(self.connect_btn)
        conn_buttons.addWidget(self.disconnect_btn)
        conn_buttons.addWidget(self.start_server_btn)
        conn_form.addRow(conn_buttons)
        layout.addWidget(conn_box)

        laser_box = QGroupBox("激光")
        laser_layout = QHBoxLayout(laser_box)
        self.laser_on_btn = QPushButton("Laser ON")
        self.laser_off_btn = QPushButton("Laser OFF")
        self.alignment_btn = QPushButton("对光监视")
        self.laser_on_btn.clicked.connect(lambda: self._run_task("laser_on", self._controller.laser_on))
        self.laser_off_btn.clicked.connect(lambda: self._run_task("laser_off", self._controller.laser_off))
        self.alignment_btn.clicked.connect(self._open_alignment_dialog)
        laser_layout.addWidget(self.laser_on_btn)
        laser_layout.addWidget(self.laser_off_btn)
        laser_layout.addWidget(self.alignment_btn)
        layout.addWidget(laser_box)

        scan_box = QGroupBox("扫描参数")
        scan_form = QFormLayout(scan_box)
        self.start_spin = self._double_spin(1200.0, 1700.0, 1550.0, 4, 0.01)
        self.stop_spin = self._double_spin(1200.0, 1700.0, 1550.1, 4, 0.01)
        self.step_combo = QComboBox()
        for step_pm in ALLOWED_STEP_PM:
            step_nm = step_pm / 1000
            self.step_combo.addItem(f"{step_pm:g} pm ({step_nm:g} nm)", step_nm)
        self.step_combo.setCurrentIndex(list(ALLOWED_STEP_PM).index(10))
        self.step_combo.currentIndexChanged.connect(self._update_speed_choices)
        self.speed_combo = QComboBox()
        self.power_spin = self._double_spin(-20.0, 20.0, 0.0, 2, 0.5)
        self.sweep_mode_combo = QComboBox()
        self.sweep_mode_combo.addItems(["1 - Continuous One-way"])
        self.range_combo = QComboBox()
        for value, text in [
            (1, "Range 1 (-30 to +10 dBm)"),
            (2, "Range 2 (-40 to 0 dBm)"),
            (3, "Range 3 (-50 to -10 dBm)"),
            (4, "Range 4 (-60 to -20 dBm)"),
            (5, "Range 5 (-80 to -30 dBm)"),
        ]:
            self.range_combo.addItem(text, value)
        self.module_spin = self._int_spin(0, 4, 0)
        self.channel_checks: list[QCheckBox] = []
        channel_widget = QWidget()
        channel_layout = QHBoxLayout(channel_widget)
        channel_layout.setContentsMargins(0, 0, 0, 0)
        for channel in range(1, 5):
            check = QCheckBox(f"CH{channel}")
            check.setChecked(channel == 1)
            self.channel_checks.append(check)
            channel_layout.addWidget(check)
        channel_layout.addStretch()
        scan_form.addRow("Start (nm)", self.start_spin)
        scan_form.addRow("Stop (nm)", self.stop_spin)
        scan_form.addRow("Step", self.step_combo)
        scan_form.addRow("Speed (nm/s)", self.speed_combo)
        scan_form.addRow("Power (dBm)", self.power_spin)
        scan_form.addRow("Sweep mode", self.sweep_mode_combo)
        scan_form.addRow("MPM range", self.range_combo)
        scan_form.addRow("MPM module", self.module_spin)
        scan_form.addRow("MPM channels", channel_widget)
        layout.addWidget(scan_box)
        self._update_speed_choices()

        action_box = QGroupBox("操作")
        action_layout = QGridLayout(action_box)
        self.save_check = QCheckBox("扫描后保存 CSV")
        self.save_check.setChecked(True)
        self.save_path_edit = QLineEdit(str(Path.cwd() / "scan_result_raw.csv"))
        browse_btn = QPushButton("选择")
        browse_btn.clicked.connect(self._choose_csv_path)
        self.scan_btn = QPushButton("单次扫描")
        self.scan_btn.clicked.connect(self._run_scan)
        self.save_btn = QPushButton("保存当前结果")
        self.save_btn.clicked.connect(self._save_last_result)
        self.use_reference_check = QCheckBox("Use reference")
        self.set_reference_btn = QPushButton("Set reference")
        self.clear_reference_btn = QPushButton("Clear reference")
        self.view_reference_btn = QPushButton("View reference")
        self.set_reference_btn.clicked.connect(self._set_reference)
        self.clear_reference_btn.clicked.connect(self._clear_reference)
        self.view_reference_btn.clicked.connect(self._view_reference)
        action_layout.addWidget(self.save_check, 0, 0, 1, 2)
        action_layout.addWidget(self.save_path_edit, 1, 0)
        action_layout.addWidget(browse_btn, 1, 1)
        action_layout.addWidget(self.scan_btn, 2, 0, 1, 2)
        action_layout.addWidget(self.save_btn, 3, 0, 1, 2)
        action_layout.addWidget(self.use_reference_check, 4, 0, 1, 2)
        action_layout.addWidget(self.set_reference_btn, 5, 0)
        action_layout.addWidget(self.clear_reference_btn, 5, 1)
        action_layout.addWidget(self.view_reference_btn, 6, 0, 1, 2)
        layout.addWidget(action_box)

        layout.addStretch()
        return panel

    def _build_output(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.status_label = QLabel("未连接")
        self.plot_canvas = PlotCanvas()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(180)
        layout.addWidget(self.status_label)
        layout.addWidget(self.plot_canvas, 1)
        layout.addWidget(QLabel("日志"))
        layout.addWidget(self.log_text)
        return panel

    def _connect(self) -> None:
        settings = self._connection_settings()
        self._run_task("connect", lambda: self._controller.connect(settings))

    def _start_remote_server(self) -> None:
        settings = self._connection_settings()
        self._run_task("start_server", lambda: self._controller.start_remote_server(settings))

    def _disconnect(self) -> None:
        self._controller.disconnect()
        self.status_label.setText("已断开")
        self._log("Disconnected")

    def _run_scan(self) -> None:
        settings = self._scan_settings()
        self._run_task("scan", lambda: self._controller.run_single_scan(settings))

    def _open_alignment_dialog(self) -> None:
        channels = self._selected_channels()
        dialog = AlignmentDialog(
            self._controller,
            self.power_spin.value(),
            self.module_spin.value(),
            channels,
            int(self.range_combo.currentData()),
            self,
        )
        dialog.show()

    def _save_last_result(self) -> None:
        if self._last_result is None:
            QMessageBox.warning(self, "无数据", "当前没有可保存的扫描结果。")
            return
        self._save_result(self._last_result)

    def _save_result(self, result: ScanResult) -> None:
        path = self.save_path_edit.text().strip()
        if not path:
            path = str(Path.cwd() / "scan_result_raw.csv")
            self.save_path_edit.setText(path)
        if self.use_reference_check.isChecked() and self._reference_result is not None:
            self._save_il_csv(result, self._reference_result, path)
        elif result.channel_powers:
            self._save_multi_raw_csv(result, path)
        else:
            self._controller.save_scan_csv(result, path)
        self._log(f"Saved CSV: {path}")

    def _save_multi_raw_csv(self, result: ScanResult, path: str) -> None:
        with open(path, "w", encoding="utf-8", newline="") as f:
            headers = ["wavelength_nm"]
            for channel in result.channels():
                headers.append(f"ch{channel}_raw_dbm")
            f.write(",".join(headers) + "\n")
            for idx, wl in enumerate(result.wavelengths):
                row = [f"{wl:.9f}"]
                for channel in result.channels():
                    row.append(f"{result.powers_for_channel(channel)[idx]:.9f}")
                f.write(",".join(row) + "\n")

    def _save_il_csv(self, result: ScanResult, reference: ScanResult, path: str) -> None:
        channels = result.channels()
        reference_channels = set(reference.channels())
        with open(path, "w", encoding="utf-8", newline="") as f:
            headers = ["wavelength_nm"]
            for channel in channels:
                headers.append(f"ch{channel}_raw_dbm")
                if channel in reference_channels:
                    headers.append(f"ch{channel}_reference_dbm")
                    headers.append(f"ch{channel}_insertion_loss_db")
            f.write(",".join(headers) + "\n")
            il_by_channel = {
                channel: calculate_reference_il_for_channel(reference, result, channel)
                for channel in channels
                if channel in reference_channels
            }
            for idx, wl in enumerate(result.wavelengths):
                row = [f"{wl:.9f}"]
                for channel in channels:
                    raw = result.powers_for_channel(channel)[idx]
                    row.append(f"{raw:.9f}")
                    if channel in il_by_channel:
                        il = il_by_channel[channel]
                        row.append(f"{il.reference_powers[idx]:.9f}")
                        row.append(f"{il.il[idx]:.9f}")
                f.write(",".join(row) + "\n")

    def _run_task(self, label: str, task: Callable[[], object | None]) -> None:
        if self._thread is not None:
            QMessageBox.information(self, "正在运行", "已有任务正在运行。")
            return
        self._set_busy(True)
        self._log(f"Starting {label}...")
        self._thread = QThread(self)
        self._worker = TaskWorker(label, task)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._task_finished)
        self._worker.failed.connect(self._task_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._thread_finished)
        self._thread.start()

    def _task_finished(self, result: WorkerResult) -> None:
        self._log(f"Finished {result.label}")
        if result.label == "connect":
            self.status_label.setText(f"已连接: {result.value}")
        elif result.label == "start_server":
            self.status_label.setText(f"Windows 服务已启动: {result.value}")
        elif result.label == "scan" and isinstance(result.value, ScanResult):
            self._last_result = result.value
            if self.use_reference_check.isChecked() and self._reference_result is not None:
                self.plot_canvas.plot_reference_il(result.value, self._reference_result)
                common_channels = sorted(set(result.value.channels()) & set(self._reference_result.channels()))
                if not common_channels:
                    self.status_label.setText("Reference 通道不匹配，已显示 raw 数据")
                    self._log("Reference skipped: no common channel with current scan")
                    self.plot_canvas.plot_scan(result.value)
                    return
                il = calculate_reference_il_for_channel(
                    self._reference_result,
                    result.value,
                    common_channels[0],
                )
                self.status_label.setText(
                    f"IL 完成: CH{common_channels}, {len(il.wavelengths)} points, "
                    f"{np.nanmin(il.il):.3f} to {np.nanmax(il.il):.3f} dB"
                )
            else:
                self.plot_canvas.plot_scan(result.value)
                powers = result.value.powers
                self.status_label.setText(
                    f"扫描完成: {len(result.value.wavelengths)} points, "
                    f"{np.nanmin(powers):.3f} to {np.nanmax(powers):.3f} dBm"
                )
            if self.save_check.isChecked():
                self._save_result(result.value)

    def _task_failed(self, trace: str) -> None:
        self._log(trace)
        QMessageBox.critical(self, "任务失败", trace.splitlines()[-1] if trace else "Unknown error")

    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._set_busy(False)

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
        if self._last_result is None:
            QMessageBox.warning(self, "无数据", "当前没有可记录为 reference 的扫描结果。")
            return
        self._reference_result = self._last_result
        self.use_reference_check.setChecked(True)
        self._log(f"Reference set: {len(self._reference_result.wavelengths)} points")

    def _clear_reference(self) -> None:
        self._reference_result = None
        self.use_reference_check.setChecked(False)
        self._log("Reference cleared")

    def _view_reference(self) -> None:
        if self._reference_result is None:
            QMessageBox.warning(self, "无 reference", "当前没有记录 reference。")
            return
        self.plot_canvas.plot_reference(self._reference_result)

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
        ]:
            widget.setEnabled(not busy)

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
    app = QApplication(sys.argv)
    window = ScanMainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
