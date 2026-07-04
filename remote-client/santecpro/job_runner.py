"""Execute a parsed scan job against a RemoteScanner.

Runs each segment via ``RemoteScanner.run_stsprocess_scan``, saves one CSV per
segment, and writes a ``manifest.json`` summarising the run. Direction is
already resolved in each :class:`~santecpro.jobscript.Segment` (reverse segments
carry swapped start/stop), so the runner just forwards the values.
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from santecpro.jobscript import JobSpec


@dataclass(frozen=True)
class SegmentResult:
    label: str
    direction: str
    ok: bool
    csv_path: str
    points: int
    error: str
    duration_s: float


def run_job(
    job: JobSpec,
    scanner: Any,
    outdir: str | Path,
    *,
    timestamp: str,
    keep_going: bool = False,
    log: Callable[[str], None] = print,
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
    job_dir = Path(outdir) / f"{job.name}_{timestamp}"
    job_dir.mkdir(parents=True, exist_ok=True)

    results: list[SegmentResult] = []
    total = len(job.segments)
    for i, seg in enumerate(job.segments, start=1):
        csv_name = f"{i:02d}_{seg.label}_{seg.direction}.csv"
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
            points = _write_segment_csv(job_dir / csv_name, result)
            duration = time.monotonic() - started
            log(f"      OK   {points} points -> {csv_name}")
            results.append(
                SegmentResult(seg.label, seg.direction, True, str(job_dir / csv_name),
                              points, "", duration)
            )
        except Exception as exc:  # noqa: BLE001 - report any scan failure per segment
            duration = time.monotonic() - started
            log(f"      FAIL {exc}")
            results.append(
                SegmentResult(seg.label, seg.direction, False, "", 0, str(exc), duration)
            )
            if not keep_going:
                log("stopping (pass --keep-going to continue after errors)")
                break

    _write_manifest(job_dir / "manifest.json", job, timestamp, results)
    return results


def _write_segment_csv(path: Path, result: Any) -> int:
    channels = result.channels()
    wavelengths = result.wavelengths
    monitor = result.monitor_powers
    per_channel = {c: result.powers_for_channel(c) for c in channels}
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["wavelength_nm", *[f"ch{c}_power_dbm" for c in channels], "monitor_dbm"])
        for i in range(len(wavelengths)):
            row: list[Any] = [wavelengths[i]]
            for c in channels:
                p = per_channel[c]
                row.append(p[i] if i < len(p) else "")
            row.append(monitor[i] if i < len(monitor) else "")
            writer.writerow(row)
    return len(wavelengths)


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
            "csv": Path(res.csv_path).name if res.csv_path else None,
            "points": res.points,
            "ok": res.ok,
            "error": res.error,
            "duration_s": round(res.duration_s, 3),
        })
    manifest = {"job": job.name, "timestamp": timestamp, "segments": entries}
    with path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
