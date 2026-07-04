"""Reusable DLL/STSProcess scan coordinator for the Windows server."""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from santecpro.sweep_rules import validate_sts_sweep_params

from .instruments import DllMpm, DllStsProcess, DllTsl


@dataclass(frozen=True)
class STSScanSettings:
    start_wl: float
    stop_wl: float
    step: float
    speed: float
    power: float = 0.0
    tsl_resource: str = "GPIB3::1::INSTR"
    mpm_resource: str = "GPIB0::16::INSTR"
    mpm_module: int = 0
    mpm_channel: int = 1
    mpm_channels: tuple[int, ...] = ()
    mpm_range: int = 1
    mpm_averaging_time_ms: float = 0.01
    csv_path: str | Path | None = None


@dataclass(frozen=True)
class STSScanResult:
    wavelengths: list[float]
    powers: list[float]
    monitor_powers: list[float]
    channel_powers: dict[int, list[float]]
    actual_step: float
    requested_points: int
    target_points: int
    raw_points: int
    mpm_expected_raw_points: int
    mpm_completed_points: int
    csv_path: str
    tsl_idn: str
    mpm_idn: str


def expected_points(start: float, stop: float, step: float) -> int:
    return int(round(abs(stop - start) / step)) + 1


def run_stsprocess_scan(
    settings: STSScanSettings,
    *,
    tsl: Any | None = None,
    mpm: Any | None = None,
    sts: Any | None = None,
) -> STSScanResult:
    """Run one DLL-backed STSProcess scan and return rescaled target data."""
    validate_sts_sweep_params(
        settings.start_wl,
        settings.stop_wl,
        settings.step,
        settings.speed,
    )
    owns_tsl = tsl is None
    owns_mpm = mpm is None
    tsl = tsl or DllTsl(settings.tsl_resource)
    mpm = mpm or DllMpm(settings.mpm_resource)
    sts = sts or DllStsProcess()

    powers: list[float] = []
    channel_powers: dict[int, list[float]] = {}
    actual_step = 0.0
    mpm_expected = 0
    completed_points = 0
    tsl_idn = ""
    mpm_idn = ""

    try:
        tsl.connect()
        tsl_idn = tsl.idn()
        mpm.connect()
        mpm_idn = mpm.idn()
        tsl.set_power_dbm(settings.power)
        channels = _selected_channels(settings)
        for channel in channels:
            mpm.configure_power_logging(settings.mpm_module, channel, settings.mpm_range)

        actual_step = tsl.set_sts_sweep_parameters(
            settings.start_wl,
            settings.stop_wl,
            settings.speed,
            settings.step,
        )
        sts.make_wavelength_tables(
            settings.start_wl,
            settings.stop_wl,
            settings.step,
            actual_step,
        )

        mpm.set_sts_logging_parameters(
            settings.start_wl,
            settings.stop_wl,
            settings.step,
            actual_step,
            settings.speed,
        )
        mpm_expected = mpm.get_logging_data_point()

        tsl.set_continuous_oneway_sweep_mode()
        tsl.set_waiting_for_trigger_start_mode()
        mpm.start_logging()
        tsl.start_sweep()
        try:
            tsl.wait_for_status(3000, "waiting_for_trigger")
            tsl.soft_trigger()
            wait_ms = int(abs(settings.stop_wl - settings.start_wl) / settings.speed * 1100)
            tsl.wait_for_status(max(wait_ms, 5000), "standby")
            _status, completed_points = mpm.wait_for_log_completion()
        finally:
            mpm.stop_logging(raise_on_error=False)
            tsl.stop_sweep(raise_on_error=False)

        first_channel = channels[0]
        first_raw_powers = mpm.get_channel_log_data(settings.mpm_module, first_channel)
        trigger, monitor = _read_auxiliary_data_or_synthesize(
            tsl, mpm, settings, actual_step, first_raw_powers
        )
        sts.set_tsl_monitor_rescaling(settings.mpm_averaging_time_ms)
        wavelengths: list[float] = []
        rescaled_monitor: list[float] = []
        raw_count = len(first_raw_powers)
        for channel in channels:
            raw_powers = (
                first_raw_powers
                if channel == first_channel
                else mpm.get_channel_log_data(settings.mpm_module, channel)
            )
            raw_count = max(raw_count, len(raw_powers))
            data_struct = sts.make_data_struct(settings.mpm_module, channel, settings.mpm_range)
            sts.add_reference_data(raw_powers, trigger, monitor, data_struct)
            wavelengths, rescaled_powers, rescaled_monitor = sts.rescale_reference(data_struct)
            channel_powers[int(channel)] = rescaled_powers
        powers = channel_powers[first_channel]

        csv_path = _write_csv(settings.csv_path, wavelengths, channel_powers, rescaled_monitor)
        return STSScanResult(
            wavelengths=wavelengths,
            powers=powers,
            monitor_powers=rescaled_monitor,
            channel_powers=channel_powers,
            actual_step=actual_step,
            requested_points=expected_points(settings.start_wl, settings.stop_wl, settings.step),
            target_points=len(wavelengths),
            raw_points=raw_count,
            mpm_expected_raw_points=mpm_expected,
            mpm_completed_points=completed_points,
            csv_path=csv_path,
            tsl_idn=tsl_idn,
            mpm_idn=mpm_idn,
        )
    finally:
        try:
            mpm.disconnect()
        finally:
            tsl.disconnect()


def _read_auxiliary_data_or_synthesize(
    tsl: Any,
    mpm: Any,
    settings: STSScanSettings,
    actual_step: float,
    powers: list[float],
) -> tuple[list[float], list[float]]:
    try:
        trigger = mpm.get_trigger_data(settings.mpm_module)
        monitor = tsl.get_sts_power_monitor_data(settings.speed, actual_step)
        return trigger, monitor
    except Exception:
        try:
            return mpm.get_216_monitor_data(settings.mpm_module)
        except Exception:
            return [float(i) for i in range(len(powers))], [0.0] * len(powers)


def _selected_channels(settings: STSScanSettings) -> tuple[int, ...]:
    channels = settings.mpm_channels or (settings.mpm_channel,)
    normalized = tuple(dict.fromkeys(int(ch) for ch in channels))
    if not normalized:
        raise ValueError("at least one MPM channel must be selected")
    for channel in normalized:
        if channel < 1 or channel > 4:
            raise ValueError(f"MPM channel must be 1-4, got {channel}")
    return normalized


def _write_csv(
    csv_path: str | Path | None,
    wavelengths: list[float],
    channel_powers: dict[int, list[float]],
    monitor_powers: list[float],
) -> str:
    if not csv_path:
        return ""
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        channels = sorted(channel_powers)
        writer.writerow(["wavelength_nm", *[f"ch{ch}_power_dbm" for ch in channels], "monitor_dbm"])
        for i, wavelength in enumerate(wavelengths):
            powers = [channel_powers[ch][i] if i < len(channel_powers[ch]) else "" for ch in channels]
            monitor = monitor_powers[i] if i < len(monitor_powers) else ""
            writer.writerow([wavelength, *powers, monitor])
    return str(path)
