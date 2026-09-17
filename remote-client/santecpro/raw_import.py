"""Read official/SantecPro single-range raw CSV spectra without guessing channels."""
import csv
from datetime import datetime
from pathlib import Path
import re

import numpy as np
from santecpro.results import ScanResult


def load_raw_reference(path: str | Path) -> ScanResult:
    path = Path(path)
    with path.open(newline='', encoding='utf-8-sig') as handle:
        reader = csv.reader(handle)
        metadata = []
        for row in reader:
            if row and row[0].strip() == 'Wavelength(nm)':
                headers = [v.strip() for v in row]
                break
            metadata.append(row)
        else:
            raise ValueError('未找到 Raw CSV 的 Wavelength(nm) 列')
        channels = {}
        modules = set()
        monitor = None
        for index, name in enumerate(headers[1:], 1):
            if not name:
                continue
            if name == 'Monitor-R1(dBm)' and monitor is None:
                monitor = index
                continue
            match = re.fullmatch(r'Raw_M(\d+)-Ch(\d+)-R1\(dBm\)', name)
            if not match:
                raise ValueError(f'不支持的数据列 {name}：请选择单个模块、单个 R1 曲线组的 Raw 文件，不是 Loss')
            module, channel = map(int, match.groups())
            if not 1 <= module <= 5 or not 1 <= channel <= 4 or channel in channels:
                raise ValueError('Raw 文件的模块/通道编号无效或重复')
            modules.add(module)
            channels[channel] = index
        if monitor is None or not channels or len(modules) != 1:
            raise ValueError('Raw 文件必须包含 Monitor 和同一模块的 Raw 通道')
        indices = [0, monitor, *channels.values()]
        values = []
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            try:
                values.append([float(row[i]) for i in indices])
            except (IndexError, ValueError) as exc:
                raise ValueError(f'CSV 第 {reader.line_num} 行存在缺失或非数值数据') from exc
    a = np.asarray(values, dtype=float)
    if len(a) < 2 or not np.isfinite(a).all():
        raise ValueError('Reference 至少需要两个有效波长点，且不能包含 NaN/Inf')
    delta = np.diff(a[:, 0])
    if not (np.all(delta > 0) or np.all(delta < 0)):
        raise ValueError('Reference 波长必须严格递增或递减，不能重复或乱序')
    meta = {r[0].strip(): r for r in metadata if r}
    params = {'mpm_module': modules.pop() - 1, 'mpm_channel': next(iter(channels)),
              'start_wl': float(a[0, 0]), 'stop_wl': float(a[-1, 0]),
              'reference_source': str(path.resolve())}
    for key, field, factor in [('Step','step',1), ('Speed','speed',1),
                                ('Source power','power',1), ('Averaging Time','mpm_averaging_time_ms',1000)]:
        row = meta.get(key, [])
        if len(row) > 1 and row[1].strip():
            value = float(row[1]) * factor
            if not np.isfinite(value):
                raise ValueError(f'无效的 {key} 元数据')
            params[field] = value
    for key, field in [('TSL','tsl_idn'), ('PowerMeter','mpm_idn')]:
        params[field] = ','.join(v.strip() for v in meta.get(key, [])[1:5])
    for key, field in [('PowerMonitor','power_monitor_idn'), ('TSL PM- range','tsl_pm_range'),
                        ('Power meter range','power_meter_range_dbm')]:
        row = meta.get(key, [])
        if len(row) > 1:
            params[field] = row[1].strip()
    module_row = meta.get('', [])
    for index, field in [(2, 'module_model'), (3, 'module_serial'), (4, 'module_info')]:
        if len(module_row) > index:
            params[field] = module_row[index].strip()
    # Official dBm range values are not MPM range indices. Keep unknown explicit.
    mpm_range = 0
    row = meta.get('Power meter range', [])
    if len(row) >= 6 and row[3].strip() == 'MPM ranges':
        ranges = [int(v) for v in row[4].split('+')]
        if len(ranges) < 2 or len(set(ranges)) != len(ranges) or any(v not in range(1, 6) for v in ranges):
            raise ValueError('Invalid merged MPM ranges')
        params['mpm_ranges'] = ranges
        params['range_merge_method'] = row[5]
    if len(row) >= 5 and row[3].strip() == 'MPM range' and row[4].strip():
        mpm_range = int(row[4])
        if not 1 <= mpm_range <= 5:
            raise ValueError('无效的 MPM Range 编号')
    timestamp = ''
    if metadata and len(metadata[0]) >= 2:
        try:
            timestamp = datetime.strptime(' '.join(metadata[0][:2]), '%Y/%m/%d %H:%M:%S').isoformat()
        except ValueError:
            pass  # absent date does not change measured spectral data
    powers = {ch: a[:, i + 2].copy() for i, ch in enumerate(channels)}
    return ScanResult(a[:, 0].copy(), next(iter(powers.values())), a[:, 1].copy(),
                      params, timestamp, mpm_range, powers)
