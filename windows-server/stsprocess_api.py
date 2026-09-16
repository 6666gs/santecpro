"""Pure helpers for the Windows STSProcess scan HTTP API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

import config

from santec_dll_backend.scanner import STSScanResult, STSScanSettings


def build_sts_scan_settings(data: dict[str, Any], base_dir: str) -> STSScanSettings:
    csv_name = data.get("csv_name") or data.get("csv") or ""
    csv_path = _csv_path(base_dir, csv_name)
    return STSScanSettings(
        start_wl=float(data["start_wl"]),
        stop_wl=float(data["stop_wl"]),
        step=float(data["step"]),
        speed=float(data["speed"]),
        power=float(data.get("power", 0.0)),
        tsl_resource=data.get("tsl_address") or config.TSL_ADDRESS,
        mpm_resource=data.get("mpm_address") or config.MPM_ADDRESS,
        mpm_module=int(data.get("mpm_module", 0)),
        mpm_channel=int(data.get("mpm_channel", 1)),
        mpm_channels=tuple(int(ch) for ch in data.get("mpm_channels", []) or ()),
        mpm_range=int(data.get("mpm_range", 1)),
        mpm_averaging_time_ms=float(data.get("mpm_averaging_time_ms", 0.01)),
        csv_path=csv_path,
    )


def sts_scan_result_to_dict(result: STSScanResult, request_data: dict[str, Any]) -> dict:
    scan_params = dict(request_data)
    scan_params.update({
        "actual_step": result.actual_step,
        "requested_points": result.requested_points,
        "target_points": result.target_points,
        "raw_points": result.raw_points,
        "mpm_expected_raw_points": result.mpm_expected_raw_points,
        "mpm_completed_points": result.mpm_completed_points,
        "csv_path": result.csv_path,
    })
    return {
        "wavelengths": result.wavelengths,
        "powers": result.powers,
        "monitor_powers": result.monitor_powers,
        "channel_powers": {str(ch): powers for ch, powers in result.channel_powers.items()},
        "scan_params": scan_params,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mpm_range": request_data.get("mpm_range", 1),
        "actual_step": result.actual_step,
        "requested_points": result.requested_points,
        "target_points": result.target_points,
        "raw_points": result.raw_points,
        "mpm_expected_raw_points": result.mpm_expected_raw_points,
        "mpm_completed_points": result.mpm_completed_points,
        "csv_path": result.csv_path,
        "tsl_idn": result.tsl_idn,
        "mpm_idn": result.mpm_idn,
    }


def _csv_path(base_dir: str, csv_name: str) -> str:
    if not csv_name:
        return ""
    if ":" in csv_name or "\\" in csv_name or "/" in csv_name or csv_name in (".", ".."):
        raise ValueError("csv_name must be a filename, not a path")
    return str(Path(base_dir) / "scan_jobs" / os.path.basename(csv_name))
