"""Execute a parsed scan job against a RemoteScanner.

Runs each segment via ``RemoteScanner.run_stsprocess_scan``, saves one CSV per
segment, and writes a ``manifest.json`` summarising the run. Direction is
already resolved in each :class:`~santecpro.jobscript.Segment` (reverse segments
carry swapped start/stop), so the runner just forwards the values.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from santecpro.jobscript import JobSpec, Segment
from santecpro.exceptions import ScanCancelled
from santecpro.session import ScanSession, ScanRecord
from santecpro.exporter import save_record_csv


@dataclass(frozen=True)
class SegmentResult:
    label: str
    direction: str
    ok: bool
    csv_path: str
    points: int
    error: str
    duration_s: float
    record: ScanRecord | None = None


def csv_filename(job: JobSpec, seg: Segment, index: int, kind: str) -> str:
    """Keep legacy names unless a device name is configured."""
    if job.device:
        return (f"{job.device}_{index:02d}_{seg.label}_"
                f"{seg.start_wl:g}-{seg.stop_wl:g}nm_{seg.step * 1000:g}pm_"
                f"{seg.speed:g}nms_{seg.direction}_{kind}.csv")
    return f"{index:02d}_{seg.label}_{seg.direction}_{kind}.csv"


def run_job(
    job: JobSpec,
    scanner: Any,
    outdir: str | Path,
    *,
    timestamp: str,
    keep_going: bool = False,
    session: ScanSession | None = None,
    reference_first: bool = False,
    reference_ready: Callable[[], None] | None = None,
    save_kind: str = "raw",
    log: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
) -> list[SegmentResult]:
    """Run every segment of *job*, saving CSVs and a manifest under *outdir*.

    Args:
        job: Parsed job specification.
        scanner: A connected ``RemoteScanner`` (or any object exposing
            ``run_stsprocess_scan``).
        outdir: Base output directory; a ``<job>_<timestamp>/`` folder is made.
        timestamp: Folder-name timestamp (passed in for deterministic output).
        keep_going: Continue after a segment fails instead of stopping.
        log: Progress sink (defaults to ``print``).

    Returns:
        One :class:`SegmentResult` per segment that ran (fewer than the job's
        segments if it stopped early on an error).
    """
    session = session if session is not None else ScanSession()
    if reference_first and len(job.segments) > 1 and reference_ready is None:
        raise ValueError("Provide reference_ready to switch the optical path after the reference scan")
    if save_kind not in ("raw", "loss"):
        raise ValueError("save_kind must be raw or loss")
    if save_kind == "loss" and session.reference is None and not reference_first:
        raise ValueError("Loss export requires a measured reference (reference_first=True)")
    job_dir = Path(outdir) / f"{job.name}_{timestamp}"
    job_dir.mkdir(parents=True, exist_ok=False)  # never overwrite an earlier run

    results: list[SegmentResult] = []
    total = len(job.segments)
    for i, seg in enumerate(job.segments, start=1):
        is_reference = reference_first and i == 1
        kind = "raw" if is_reference else save_kind
        csv_name = csv_filename(job, seg, i, kind)
        record = None
        log(
            f"[{i}/{total}] {seg.label} ({seg.direction}) "
            f"{seg.start_wl:g} -> {seg.stop_wl:g} nm  "
            f"step={seg.step * 1000:g}pm speed={seg.speed:g}nm/s"
        )
        started = time.monotonic()
        try:
            result = scanner.run_stsprocess_scan(
                start_wl=seg.start_wl,
                stop_wl=seg.stop_wl,
                step=seg.step,
                speed=seg.speed,
                power=seg.power,
                mpm_range=seg.mpm_range,
                mpm_channel=seg.mpm_channels[0],
                mpm_channels=seg.mpm_channels,
                mpm_averaging_time_ms=seg.mpm_averaging_time_ms,
                plot=False,
                save_csv=None,
            )
            record = session.add(result, is_reference=is_reference)
            save_record_csv(record, str(job_dir / csv_name), kind)
            points = len(record.raw.wavelengths)
            duration = time.monotonic() - started
            log(f"      OK   {points} points -> {csv_name}")
            results.append(
                SegmentResult(seg.label, seg.direction, True, str(job_dir / csv_name),
                              points, "", duration, record)
            )
        except Exception as exc:  # noqa: BLE001 - report any scan failure per segment
            duration = time.monotonic() - started
            log(f"      FAIL {exc}")
            results.append(
                SegmentResult(seg.label, seg.direction, False, "", 0, str(exc), duration, record)
            )
            if is_reference or not keep_going or isinstance(exc, (ScanCancelled, TimeoutError, ConnectionError)):
                log("stopping: cancellation/connection uncertainty or stop-on-error policy")
                break
        finally:
            _write_manifest(job_dir / "manifest.json", job, timestamp, results)
        if is_reference and i < total:
            reference_ready()
        if seg.wait_after_s:
            log(f"      waiting {seg.wait_after_s:g}s (Ctrl+C to stop)")
            sleep(seg.wait_after_s)

    _write_manifest(job_dir / "manifest.json", job, timestamp, results)
    return results


def _write_manifest(path: Path, job: JobSpec, timestamp: str, results: list[SegmentResult]) -> None:
    entries = []
    for seg, res in zip(job.segments, results):
        entries.append({
            "label": seg.label,
            "direction": seg.direction,
            "start_wl": seg.start_wl,
            "stop_wl": seg.stop_wl,
            "step_nm": seg.step,
            "speed_nm_s": seg.speed,
            "power_dbm": seg.power,
            "mpm_range": seg.mpm_range,
            "channels": list(seg.mpm_channels),
            "averaging_ms": seg.mpm_averaging_time_ms,
            "wait_after_s": seg.wait_after_s,
            "csv": Path(res.csv_path).name if res.csv_path else None,
            "points": res.points,
            "ok": res.ok,
            "error": res.error,
            "duration_s": round(res.duration_s, 3),
            "is_reference": bool(res.record and res.record.is_reference),
            "reference_index": res.record.reference_index if res.record else None,
            "loss_available": bool(res.record and res.record.loss),
            "loss_error": res.record.loss_error if res.record else "",
            "loss_convention": "reference_dbm - measurement_dbm",
        })
    manifest = {"job": job.name, "device": job.device, "timestamp": timestamp, "segments": entries}
    with path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
