"""Reusable DLL/STSProcess scan coordinator for the Windows server."""

from __future__ import annotations

import csv
import math
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from santecpro.sweep_rules import validate_sts_sweep_params

from .instruments import DllMpm, DllSpu, DllStsProcess, DllTsl, check_cancelled


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
    daq_device: str = ""


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
    averaging_time_ms: float | None = None


def expected_points(start: float, stop: float, step: float) -> int:
    return int(round(abs(stop - start) / step)) + 1


def run_stsprocess_scan(
    settings: STSScanSettings,
    *,
    tsl: Any | None = None,
    mpm: Any | None = None,
    sts: Any | None = None,
    cancel_event=None,
    spu: Any | None = None,
) -> STSScanResult:
    """Run one DLL-backed STSProcess scan and return rescaled target data."""
    validate_sts_sweep_params(
        settings.start_wl,
        settings.stop_wl,
        settings.step,
        settings.speed,
    )
    channels = _selected_channels(settings)
    if not math.isfinite(settings.power):
        raise ValueError("power must be finite")
    if not math.isfinite(settings.mpm_averaging_time_ms) or settings.mpm_averaging_time_ms <= 0:
        raise ValueError("averaging time must be positive and finite")
    if settings.mpm_range not in range(1, 6) or settings.mpm_module not in range(5):
        raise ValueError("MPM range must be 1-5 and module must be 0-4")
    check_cancelled(cancel_event)
    tsl = tsl or DllTsl(settings.tsl_resource)
    mpm = mpm or DllMpm(settings.mpm_resource)
    sts = sts or DllStsProcess()
    if spu is None and settings.daq_device:
        spu = DllSpu(settings.daq_device)

    powers: list[float] = []
    channel_powers: dict[int, list[float]] = {}
    actual_step = 0.0
    mpm_expected = 0
    completed_points = 0
    tsl_idn = ""
    mpm_idn = ""

    tsl_connected = mpm_connected = spu_connected = False
    averaging_ms = settings.mpm_averaging_time_ms
    try:
        tsl.connect()
        tsl_connected = True
        tsl_idn = tsl.idn()
        if not tsl.laser_is_on():
            raise RuntimeError("Laser is not ready. Initialize and wait for warmup before scanning.")
        mpm.connect()
        mpm_connected = True
        mpm_idn = mpm.idn()
        if spu is not None:
            spu.connect()
            spu_connected = True
            logging.getLogger(__name__).info("STS auxiliary source: NI DAQ/SPU %s", settings.daq_device)
        tsl.set_power_dbm(settings.power)
        for channel in channels:
            mpm.configure_power_logging(settings.mpm_module, channel, settings.mpm_range)

        actual_step = tsl.set_sts_sweep_parameters(
            settings.start_wl,
            settings.stop_wl,
            settings.speed,
            settings.step,
        )
        if not math.isfinite(actual_step) or actual_step <= 0:
            raise RuntimeError("TSL returned an invalid trigger step")
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
            0.0 if spu is not None else actual_step,
            settings.speed,
        )
        mpm_expected = mpm.get_logging_data_point()
        if spu is not None:
            averaging_ms = mpm.get_averaging_time_ms()
            if not math.isfinite(averaging_ms) or averaging_ms <= 0:
                raise RuntimeError("MPM returned invalid averaging time")
            spu.configure(settings.start_wl, settings.stop_wl, settings.speed,
                          actual_step, averaging_ms)
            logging.getLogger(__name__).info(
                "STS DAQ configured: trigger_step=%s nm, MPM averaging=%s ms, expected_points=%s",
                actual_step, averaging_ms, mpm_expected)

        tsl.set_continuous_oneway_sweep_mode()
        tsl.set_waiting_for_trigger_start_mode()
        check_cancelled(cancel_event)
        try:
            mpm.start_logging()
            tsl.start_sweep()
            tsl.wait_for_status(3000, "waiting_for_trigger", cancel_event=cancel_event)
            if spu is not None:
                spu.start_sampling()
            tsl.soft_trigger()
            check_cancelled(cancel_event)
            wait_ms = int(abs(settings.stop_wl - settings.start_wl) / settings.speed * 1100)
            tsl.wait_for_status(max(wait_ms, 5000), "standby", cancel_event=cancel_event)
            if spu is not None:
                spu.wait_for_completion(timeout_s=10, cancel_event=cancel_event)
            _status, completed_points = mpm.wait_for_log_completion(
                expected_points=mpm_expected, cancel_event=cancel_event
            )
        finally:
            _cleanup([
                lambda: mpm.stop_logging(), lambda: tsl.stop_sweep(),
            ])

        check_cancelled(cancel_event)
        if completed_points != mpm_expected or completed_points <= 0:
            raise RuntimeError(f"Incomplete MPM acquisition: expected {mpm_expected}, got {completed_points}")
        first_channel = channels[0]
        first_raw_powers = mpm.get_channel_log_data(settings.mpm_module, first_channel)
        if spu is not None:
            trigger, monitor = spu.get_sampling_raw_data()
            logging.getLogger(__name__).info(
                "STS DAQ read: trigger=%s, monitor=%s, MPM=%s points",
                len(trigger), len(monitor), completed_points)
            _validate_values(trigger, "DAQ trigger data")
            _validate_values(monitor, "DAQ monitor data")
            sts.set_spu_rescaling(averaging_ms)
        else:
            trigger, monitor = _read_auxiliary_data(tsl, mpm, settings, actual_step)
            sts.set_tsl_monitor_rescaling(averaging_ms)
        wavelengths: list[float] = []
        rescaled_monitor: list[float] = []
        raw_count = len(first_raw_powers)
        first_wavelengths = None
        for channel in channels:
            check_cancelled(cancel_event)
            raw_powers = (
                first_raw_powers
                if channel == first_channel
                else mpm.get_channel_log_data(settings.mpm_module, channel)
            )
            _validate_values(raw_powers, f"CH{channel} raw powers")
            if len(raw_powers) != completed_points:
                raise RuntimeError(f"CH{channel} raw point count does not match completed acquisition")
            raw_count = max(raw_count, len(raw_powers))
            data_struct = sts.make_data_struct(settings.mpm_module, channel, settings.mpm_range)
            sts.add_reference_data(raw_powers, trigger, monitor, data_struct)
            wavelengths, rescaled_powers, rescaled_monitor = sts.rescale_reference(data_struct)
            _validate_values(wavelengths, "wavelengths")
            _validate_values(rescaled_powers, f"CH{channel} rescaled powers")
            _validate_values(rescaled_monitor, "rescaled monitor")
            expected = expected_points(settings.start_wl, settings.stop_wl, settings.step)
            if not (len(wavelengths) == len(rescaled_powers) == len(rescaled_monitor) == expected):
                raise RuntimeError("Rescaled data lengths do not match requested wavelength grid")
            direction = 1 if settings.stop_wl > settings.start_wl else -1
            if any((b - a) * direction <= 0 for a, b in zip(wavelengths, wavelengths[1:])):
                raise RuntimeError("Wavelength order does not match scan direction")
            if abs(wavelengths[0] - settings.start_wl) > settings.step / 2 or abs(wavelengths[-1] - settings.stop_wl) > settings.step / 2 + 1e-8:
                raise RuntimeError("Returned wavelength span does not match requested span")
            if first_wavelengths is not None and wavelengths != first_wavelengths:
                raise RuntimeError("Channel wavelength grids do not match")
            first_wavelengths = list(wavelengths)
            channel_powers[int(channel)] = rescaled_powers
        powers = channel_powers[first_channel]

        check_cancelled(cancel_event)
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
            averaging_time_ms=averaging_ms,
        )
    finally:
        actions = []
        if spu_connected:
            actions.extend([spu.stop_sampling, spu.disconnect])
        if mpm_connected:
            actions.append(mpm.disconnect)
        if tsl_connected:
            actions.append(tsl.disconnect)
        _cleanup(actions)


def _cleanup(actions):
    """Attempt every cleanup action, preserving the original scan exception."""
    active_error = sys.exc_info()[0] is not None
    errors = []
    for action in actions:
        try:
            action()
        except Exception as exc:
            logging.getLogger(__name__).exception("Instrument cleanup failed")
            errors.append(exc)
    if errors and not active_error:
        raise RuntimeError(f"Instrument cleanup failed: {errors}") from errors[0]


def _validate_values(values, label):
    if not values or not all(math.isfinite(float(value)) for value in values):
        raise RuntimeError(f"Missing or non-finite {label}")


def _read_auxiliary_data(
    tsl: Any,
    mpm: Any,
    settings: STSScanSettings,
    actual_step: float,
) -> tuple[list[float], list[float]]:
    try:
        trigger = mpm.get_trigger_data(settings.mpm_module)
        monitor = tsl.get_sts_power_monitor_data(settings.speed, actual_step)
        _validate_values(trigger, "trigger data")
        _validate_values(monitor, "TSL monitor data")
        return trigger, monitor
    except Exception as primary_error:
        try:
            trigger, monitor = mpm.get_216_monitor_data(settings.mpm_module)
            _validate_values(trigger, "MPM trigger data")
            _validate_values(monitor, "MPM monitor data")
            return trigger, monitor
        except Exception as fallback_error:
            raise RuntimeError(
                f"Cannot obtain measured trigger/monitor data; refusing synthetic data. "
                f"For NI USB-6210 configure SANTEC_DAQ_DEVICE=Dev1 on Windows and restart server. "
                f"Primary: {primary_error}; fallback: {fallback_error}"
            ) from fallback_error


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
