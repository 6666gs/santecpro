"""In-memory scan history and references measured during this session."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

import numpy as np

from santecpro.reference import calculate_reference_il_for_channel
from santecpro.results import ScanResult


@dataclass
class ScanRecord:
    raw: ScanResult
    loss: dict[int, np.ndarray] = field(default_factory=dict)
    reference_index: int | None = None
    is_reference: bool = False
    loss_error: str = ""


class ScanSession:
    """Keep raw and calculated loss independent of display/export selection.

    Loss is positive insertion loss: reference dBm minus measurement dBm.
    A new reference affects future scans only. Nothing is imported from disk.
    """
    def __init__(self):
        self.records: list[ScanRecord] = []
        self.reference_index: int | None = None

    @property
    def reference(self) -> ScanResult | None:
        if self.reference_index is None:
            return None
        return self.records[self.reference_index].raw

    def add(self, raw: ScanResult, *, is_reference: bool = False) -> ScanRecord:
        record = ScanRecord(raw=deepcopy(raw), is_reference=is_reference)
        if is_reference:
            record.loss_error = "Reference 只保存 raw"
        elif self.reference is None:
            record.loss_error = "尚未扫描并设置 reference，loss 不可用"
        else:
            record.reference_index = self.reference_index
            try:
                if raw.scan_params.get("mpm_module", 0) != self.reference.scan_params.get("mpm_module", 0):
                    raise ValueError("Reference 与测量的模块不匹配")
                missing = set(raw.channels()) - set(self.reference.channels())
                if missing:
                    raise ValueError(f"Reference 缺少通道 {sorted(missing)}")
                record.loss = {
                    ch: calculate_reference_il_for_channel(self.reference, record.raw, ch).il.copy()
                    for ch in record.raw.channels()
                }
            except ValueError as exc:
                record.loss_error = str(exc)
        self.records.append(record)
        if is_reference:
            self.reference_index = len(self.records) - 1
        return record

    def set_reference(self, index: int) -> None:
        record = self.records[index]
        record.is_reference = True
        record.loss = {}
        record.reference_index = None
        record.loss_error = "Reference 只保存 raw"
        self.reference_index = index

    def clear_reference(self) -> None:
        self.reference_index = None
