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
    sequence: int = 0
    saved: bool = False

    @property
    def array_bytes(self) -> int:
        arrays = [self.raw.wavelengths, self.raw.powers, self.raw.monitor_powers,
                  *self.raw.channel_powers.values(), *self.loss.values()]
        return sum(a.nbytes for a in {id(a): a for a in arrays}.values())


class ScanSession:
    """Keep raw and calculated loss independent of display/export selection.

    Loss is positive insertion loss: reference dBm minus measurement dBm.
    A new reference affects future scans only. Nothing is imported from disk.
    """
    def __init__(self):
        self.records: list[ScanRecord] = []
        self._sequence = 0
        self.reference_index: int | None = None

    @property
    def reference(self) -> ScanResult | None:
        if self.reference_index is None:
            return None
        return self.records[self.reference_index].raw

    def add(self, raw: ScanResult, *, is_reference: bool = False) -> ScanRecord:
        self._sequence += 1
        record = ScanRecord(raw=deepcopy(raw), is_reference=is_reference, sequence=self._sequence)
        if is_reference:
            record.loss_error = "Reference 只保存 raw"
        elif self.reference is None:
            record.loss_error = "尚未扫描并设置 reference，loss 不可用"
        else:
            record.reference_index = self.records[self.reference_index].sequence - 1
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

    @property
    def array_bytes(self) -> int:
        return sum(record.array_bytes for record in self.records)

    def trim_saved(self, *, max_records: int = 20, max_bytes: int = 256 * 1024**2,
                   keep: ScanRecord | None = None) -> int:
        """Evict oldest exported records; never discard unsaved data or active reference.

        Limits concern resident array payloads, not total process RSS. Reference,
        newest and explicitly selected records remain even if individually oversized.
        Sequence numbers (including loss provenance) never change after eviction.
        """
        reference = self.records[self.reference_index] if self.reference_index is not None else None
        newest = self.records[-1] if self.records else None
        count = 0
        size = self.array_bytes
        for record in list(self.records):
            if len(self.records) <= max_records and size <= max_bytes:
                break
            if not record.saved or any(record is item for item in (reference, newest, keep)):
                continue
            self.records = [item for item in self.records if item is not record]
            size -= record.array_bytes
            count += 1
        self.reference_index = next((i for i, item in enumerate(self.records) if item is reference), None)
        return count
