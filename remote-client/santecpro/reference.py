"""Reference spectrum helpers for insertion-loss measurements."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from santecpro.results import ScanResult


@dataclass(frozen=True)
class ReferenceILResult:
    wavelengths: np.ndarray
    measurement_powers: np.ndarray
    reference_powers: np.ndarray
    il: np.ndarray


def calculate_reference_il(reference: ScanResult, measurement: ScanResult) -> ReferenceILResult:
    """Interpolate a reference scan and calculate insertion loss.

    IL is defined as ``reference_power - measurement_power`` in dB.
    """
    ref_wl = np.asarray(reference.wavelengths, dtype=float)
    ref_power = np.asarray(reference.powers, dtype=float)
    meas_wl = np.asarray(measurement.wavelengths, dtype=float)
    meas_power = np.asarray(measurement.powers, dtype=float)

    if ref_wl.size == 0 or meas_wl.size == 0:
        raise ValueError("reference and measurement scans must not be empty")
    if np.nanmin(meas_wl) < np.nanmin(ref_wl) or np.nanmax(meas_wl) > np.nanmax(ref_wl):
        raise ValueError("measurement wavelength span is outside reference wavelength span")

    order = np.argsort(ref_wl)
    interp_ref = np.interp(meas_wl, ref_wl[order], ref_power[order])
    return ReferenceILResult(
        wavelengths=meas_wl.copy(),
        measurement_powers=meas_power.copy(),
        reference_powers=interp_ref,
        il=interp_ref - meas_power,
    )


def calculate_reference_il_for_channel(
    reference: ScanResult,
    measurement: ScanResult,
    channel: int,
) -> ReferenceILResult:
    """Calculate interpolated IL for one MPM channel."""
    ref = ScanResult(
        wavelengths=reference.wavelengths,
        powers=reference.powers_for_channel(channel),
        monitor_powers=reference.monitor_powers,
        scan_params=reference.scan_params,
        timestamp=reference.timestamp,
        mpm_range=reference.mpm_range,
        channel_powers={channel: reference.powers_for_channel(channel)},
    )
    meas = ScanResult(
        wavelengths=measurement.wavelengths,
        powers=measurement.powers_for_channel(channel),
        monitor_powers=measurement.monitor_powers,
        scan_params=measurement.scan_params,
        timestamp=measurement.timestamp,
        mpm_range=measurement.mpm_range,
        channel_powers={channel: measurement.powers_for_channel(channel)},
    )
    return calculate_reference_il(ref, meas)
