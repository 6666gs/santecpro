"""GUI script sequencing; timers run on the UI thread, scans use its worker."""
from datetime import datetime
from pathlib import Path
import time

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                            QTextEdit, QFileDialog, QMessageBox, QCheckBox, QLabel)
from santecpro.jobscript import parse_job
from santecpro.job_runner import csv_filename, SegmentResult, _write_manifest, record_info, reserve_output_path, new_output_file
from santecpro.exporter import save_record_csv
from santecpro.ui_controller import ScanSettings


class ScriptUiMixin:
    def _init_script(self):
        self._script_job = None
        self._script_path = Path(__file__).parents[1] / 'jobs' / 'device_two_pass.scan'
        self._script_paused = False
        self._script_stopped = False
        self._script_timer = QTimer(self)
        self._script_timer.setInterval(100)
        self._script_timer.timeout.connect(self._script_tick)
        self.script_dialog = QDialog(self)
        self.script_dialog.setWindowTitle('扫描脚本')
        self.script_dialog.resize(680, 460)
        layout = QVBoxLayout(self.script_dialog)
        self.script_editor = QTextEdit()
        self.script_editor.setAcceptRichText(False)
        self.script_editor.setPlainText(self._script_path.read_text(encoding='utf-8'))
        layout.addWidget(QLabel("按脚本逐段扫描并自动保存；导出类型沿用主界面 Raw / Loss 选择；NI DAQ 平均时间自动确定。"))
        layout.addWidget(self.script_editor)
        self.script_review_check = QCheckBox('每段结束后手动继续（不限查看时间）')
        layout.addWidget(self.script_review_check)
        row = QHBoxLayout()
        for title, callback in [('打开 .scan…', self._load_script),
                                ('另存脚本…', self._save_script),
                                ('运行脚本', self._start_script)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)

    def _load_script(self):
        path, _ = QFileDialog.getOpenFileName(self, '打开扫描脚本', str(self._script_path), 'Scan (*.scan)')
        if path:
            try:
                text = Path(path).read_text(encoding='utf-8')
                self.script_editor.setPlainText(text)
                self._script_path = Path(path)
            except OSError as exc:
                QMessageBox.warning(self, '读取失败', str(exc))

    def _save_script(self):
        path, _ = QFileDialog.getSaveFileName(self, '保存扫描脚本', str(self._script_path), 'Scan (*.scan)')
        if path:
            try:
                Path(path).write_text(self.script_editor.toPlainText(), encoding='utf-8')
                self._script_path = Path(path)
            except OSError as exc:
                QMessageBox.warning(self, '保存失败', str(exc))

    def _start_script(self):
        if self._script_job is not None or self._thread is not None:
            return
        if self._preview or not self._controller.laser_ready:
            QMessageBox.information(self, '尚未就绪', '请先连接仪器并等待激光就绪；预览模式不运行扫描。')
            return
        try:
            job = parse_job(self.script_editor.toPlainText(), default_name=self._script_path.stem)
            if not job.segments:
                raise ValueError('脚本没有扫描段')
            kind = self.export_combo.currentData()
            if kind == 'loss' and self._session.reference is None:
                raise ValueError('请先在界面扫描线路 Reference，再保存 Loss')
            output = Path(job.output).expanduser() if job.output else Path.cwd() / 'scan_results'
            if not output.is_absolute():
                output = self._script_path.resolve().parent / output
            self._script_stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            self._script_dir = output
            self._script_dir.mkdir(parents=True, exist_ok=True)
            self._script_manifest = reserve_output_path(self._script_dir / 'manifest.json')
        except Exception as exc:
            QMessageBox.warning(self, '脚本无法运行', str(exc))
            return
        self._script_job = job
        self._script_kind = kind
        self._script_module = self.module_spin.value()
        self._script_results = []
        self._script_index = 0
        self._script_paused = False
        self._script_stopped = False
        self._script_error = ""
        self._script_review = self.script_review_check.isChecked()
        self.script_dialog.hide()
        self._log(f'脚本输出：{self._script_dir}')
        self._script_next()

    def _script_next(self):
        if self._script_stopped or self._script_index >= len(self._script_job.segments):
            self._finish_script()
            return
        seg = self._script_job.segments[self._script_index]
        self.start_spin.setValue(seg.start_wl)
        self.stop_spin.setValue(seg.stop_wl)
        self.step_combo.setCurrentIndex(self.step_combo.findData(seg.step))
        self.speed_combo.setCurrentIndex(self.speed_combo.findData(seg.speed))
        self.power_spin.setValue(seg.power)
        self.range_combo.setCurrentIndex(self.range_combo.findData(seg.mpm_range))
        self.multi_range_check.setChecked(bool(seg.mpm_ranges))
        for rng, check in enumerate(self.range_checks, 1):
            check.setChecked(rng in seg.mpm_ranges)
        for channel, check in enumerate(self.channel_checks, 1):
            check.setChecked(channel in seg.mpm_channels)
        settings = ScanSettings(seg.start_wl, seg.stop_wl, seg.step, seg.speed,
                                seg.power, 1, seg.mpm_range, self._script_module,
                                seg.mpm_channels[0], seg.mpm_averaging_time_ms, seg.mpm_channels, seg.mpm_ranges)
        self._script_started = time.monotonic()
        self._run_task('script_scan', lambda: self._controller.run_single_scan(settings))
        self.status_label.setText(f'脚本 {self._script_index + 1}/{len(self._script_job.segments)}：{seg.label} 扫描中')

    def _script_result(self, raw):
        seg = self._script_job.segments[self._script_index]
        raw.scan_params.setdefault('tsl_idn', self._controller._tsl_idn)
        raw.scan_params.setdefault('mpm_idn', self._controller._mpm_idn)
        record = self._session.add(raw)
        index = len(self._session.records) - 1
        self.history_combo.addItem(f'#{record.sequence} {seg.label} {raw.timestamp}')
        self.history_combo.setCurrentIndex(index)
        self._select_history(index)
        path = self._script_dir / csv_filename(self._script_job, seg, self._script_index + 1, self._script_kind)
        error = ''
        try:
            with new_output_file(path) as target:
                save_record_csv(record, str(target), self._script_kind)
            path = target
            record.saved = True
            self._log(f'Saved {self._script_kind}: {path}')
        except Exception as exc:
            error = str(exc)
            self._script_stopped = True
        self._script_results.append(SegmentResult(seg.label, seg.direction, not error,
            str(path) if not error else '', len(raw.wavelengths), error,
            time.monotonic() - self._script_started, record_info=record_info(record)))
        self._trim_history()
        self._script_remaining = seg.wait_after_s
        self._script_index += 1
        try:
            _write_manifest(self._script_manifest, self._script_job,
                            self._script_stamp, self._script_results)
        except OSError as exc:
            error = str(exc)
            self._script_stopped = True
        if error:
            QMessageBox.warning(self, '脚本保存失败，已停止', error)

    def _script_after_thread(self):
        if (self._script_stopped and len(self._script_results) == self._script_index
                and self._script_index < len(self._script_job.segments)
                and self._script_error):
            seg = self._script_job.segments[self._script_index]
            self._script_results.append(SegmentResult(seg.label, seg.direction, False, '', 0,
                self._script_error or '用户停止脚本', time.monotonic() - self._script_started))
            try:
                _write_manifest(self._script_manifest, self._script_job,
                                self._script_stamp, self._script_results)
            except OSError as exc:
                self._log(f'保存 manifest 失败：{exc}')
        if self._script_stopped or self._script_index >= len(self._script_job.segments):
            self._finish_script()
            return
        self._script_paused = self._script_paused or self._script_review
        self._script_clock = time.monotonic()
        self._set_busy(False)
        self._script_timer.start()
        self._script_tick()

    def _script_tick(self):
        now = time.monotonic()
        if not self._script_paused:
            self._script_remaining = max(0, self._script_remaining - (now - self._script_clock))
        self._script_clock = now
        state = '已暂停查看；点击继续执行下一段' if self._script_paused else f'{self._script_remaining:.1f} 秒后扫描下一段'
        self.status_label.setText(f'脚本 {self._script_index}/{len(self._script_job.segments)} 已保存 · {state}')
        if not self._script_paused and self._script_remaining <= 0:
            self._script_timer.stop()
            self._script_next()

    def _pause_script(self):
        if self._script_job is None:
            return
        self._script_paused = not self._script_paused
        if self._script_timer.isActive():
            # Continue explicitly skips the remaining review delay.
            if not self._script_paused:
                self._script_remaining = 0
            self._script_clock = time.monotonic()
            self._script_tick()
        self.script_pause_btn.setText('继续脚本' if self._script_paused else '暂停脚本')
        if self._thread is not None and self._script_paused:
            self.status_label.setText('本段扫描完成并保存后暂停')

    def _stop_script(self):
        self._script_stopped = True
        self._script_timer.stop()
        if self._thread is None:
            self._finish_script()

    def _finish_script(self):
        self._script_timer.stop()
        state = '已停止' if self._script_stopped else '已完成'
        self._script_job = None
        self.script_pause_btn.setText('暂停脚本')
        self._set_busy(False)
        self.status_label.setText(f'脚本{state}；最近结果保留在历史缓存中。输出：{self._script_dir}')
