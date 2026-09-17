"""MPM-211 sequential range merging for the real STS/DAQ endpoint.

Mirrors STSProcess 2.2.7 Range_Threshold.MergeData: ascending range index,
replace power when the accumulated power is strictly below the next range's
upper threshold; retain the first sweep's monitor. No averaging or offsets.
"""
from copy import deepcopy
import numpy as np

UPPER_DBM = {1: 10., 2: 0., 3: -10., 4: -20., 5: -30.}


def parse_ranges(data):
    values = data.get('mpm_ranges')
    if values is None or values == []:
        return (int(data.get('mpm_range', 1)),)
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError('mpm_ranges must be a nonempty list of MPM-211 ranges 1-5')
    if any(type(v) is not int or v not in UPPER_DBM for v in values):
        raise ValueError('mpm_ranges must contain integers 1-5')
    if len(set(values)) != len(values):
        raise ValueError('mpm_ranges must not contain duplicates')
    return tuple(sorted(values))


class RangeMerger:
    """Incremental merge; holds only the accumulated spectrum plus one sweep."""
    def __init__(self):
        self.result = None
        self.ranges = []
        self.sources = {}

    def add(self, data):
        rng = data['mpm_range']
        if rng not in UPPER_DBM or (self.ranges and rng <= self.ranges[-1]):
            raise ValueError('MPM-211 ranges must be distinct and ascending')
        wl = np.asarray(data['wavelengths'], dtype=float)
        channels = data['channel_powers'] or {str(data['scan_params'].get('mpm_channel', 1)): data['powers']}
        if len(wl) < 2 or not np.isfinite(wl).all() or not (np.all(np.diff(wl)>0) or np.all(np.diff(wl)<0)):
            raise ValueError('Invalid multi-range wavelength grid')
        for values in [data['monitor_powers'], data['powers'], *channels.values()]:
            if len(values) != len(wl) or not np.isfinite(values).all():
                raise ValueError('Missing or nonfinite multi-range data')
        if self.result is None:
            self.result = deepcopy(data)
            self.result['channel_powers'] = {ch: list(p) for ch, p in channels.items()}
            self.sources = {ch: np.full(len(wl), rng, dtype=np.uint8) for ch in channels}
        else:
            if not np.array_equal(wl, self.result['wavelengths']) or set(channels) != set(self.sources):
                raise ValueError('Multi-range sweeps must have identical grids and channels')
            for ch, values in channels.items():
                merged = np.asarray(self.result['channel_powers'][ch], dtype=float)
                use = merged < UPPER_DBM[rng]
                merged[use] = np.asarray(values)[use]
                self.sources[ch][use] = rng
                self.result['channel_powers'][ch] = merged.tolist()
        self.ranges.append(rng)
        primary = str(data['scan_params'].get('mpm_channel', 1))
        self.result['powers'] = self.result['channel_powers'][primary]
        self.result['timestamp'] = data['timestamp']
        self.result['mpm_range'] = 0
        self.result['scan_params'].update(
            mpm_range=0, mpm_ranges=list(self.ranges),
            range_merge_method='MPM-211 STSProcess 2.2.7 threshold selection',
            range_merge_monitor='first sweep',
            range_merge_source_counts={ch: {str(r): int(np.count_nonzero(src == r)) for r in self.ranges}
                                       for ch, src in self.sources.items()},
        )
        return self.result
