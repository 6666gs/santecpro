"""Scan result data types and pure post-processing (no hardware dependency).

This module holds the data structures returned by the remote scanner plus the
pure-numpy algorithms for multi-range merging and insertion-loss calculation.
It deliberately has **no** dependency on pyvisa or the instrument drivers, so it
can run anywhere the client runs (macOS included).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# MPM-211 module dynamic ranges: range_number -> (min_dBm, max_dBm).
# Inlined here so the client needs no instrument driver package.
MPM_RANGES: dict[int, tuple[float, float]] = {
    1: (-30, 10),
    2: (-40, 0),
    3: (-50, -10),
    4: (-60, -20),
    5: (-80, -30),
}


@dataclass
class ScanResult:
    """Holds the result of a single wavelength scan.

    Attributes:
        wavelengths: Array of wavelength values in nm.
        powers: Array of measured power values in dBm.
        monitor_powers: Array of TSL power-monitor values in dBm.
        scan_params: Dictionary of the scan parameters used.
        timestamp: ISO-8601 timestamp of when the scan completed.
        mpm_range: MPM dynamic range number (1-5) used for this scan.
    """

    wavelengths: np.ndarray
    powers: np.ndarray
    monitor_powers: np.ndarray
    scan_params: dict = field(default_factory=dict)
    timestamp: str = ""
    mpm_range: int = 1
    channel_powers: dict[int, np.ndarray] = field(default_factory=dict)

    def powers_for_channel(self, channel: int) -> np.ndarray:
        """Return powers for a channel, falling back to the legacy single trace."""
        return self.channel_powers.get(int(channel), self.powers)

    def channels(self) -> list[int]:
        """Return channels included in this result."""
        if self.channel_powers:
            return sorted(self.channel_powers)
        channel = self.scan_params.get("mpm_channel", 1)
        return [int(channel)]


@dataclass
class ILMeasurement:
    """Holds an insertion-loss measurement result.

    Attributes:
        reference: ScanResult from the reference (no-DUT) scan.
        measurement: ScanResult from the measurement (with-DUT) scan.
        il: Array of insertion-loss values in dB.
        wavelengths: Array of wavelength values corresponding to il.
    """

    reference: ScanResult
    measurement: ScanResult
    il: np.ndarray
    wavelengths: np.ndarray


def merge_multi_range(scan_results: list[ScanResult]) -> ScanResult:
    """Merge multi-range scan data into a single ScanResult.

    For each wavelength point, select the power reading from the range where
    the signal falls within the valid dynamic range.  When multiple ranges
    cover a point, prefer the *lowest* range number (best SNR).  Wavelength
    points with no valid range are filled with NaN.

    The output wavelength grid is taken from the first ScanResult.
    """
    if not scan_results:
        raise ValueError("scan_results must not be empty")

    if len(scan_results) == 1:
        return ScanResult(
            wavelengths=scan_results[0].wavelengths.copy(),
            powers=scan_results[0].powers.copy(),
            monitor_powers=scan_results[0].monitor_powers.copy(),
            scan_params=dict(scan_results[0].scan_params),
            timestamp=scan_results[0].timestamp,
            mpm_range=scan_results[0].mpm_range,
        )

    ref_wl = scan_results[0].wavelengths
    n = len(ref_wl)
    merged_powers = np.full(n, np.nan)
    merged_monitor = np.full(n, np.nan)

    sorted_results = sorted(scan_results, key=lambda sr: sr.mpm_range)

    for sr in sorted_results:
        rng = sr.mpm_range
        min_p, max_p = MPM_RANGES[rng]

        if np.array_equal(sr.wavelengths, ref_wl):
            pows = sr.powers.copy()
            mons = sr.monitor_powers.copy()
        else:
            pows = np.interp(ref_wl, sr.wavelengths, sr.powers)
            mons = np.interp(ref_wl, sr.wavelengths, sr.monitor_powers)

        valid = (pows >= min_p) & (pows <= max_p)
        unfilled = np.isnan(merged_powers)
        fill = valid & unfilled
        merged_powers[fill] = pows[fill]
        merged_monitor[fill] = mons[fill]

    return ScanResult(
        wavelengths=ref_wl.copy(),
        powers=merged_powers,
        monitor_powers=merged_monitor,
        scan_params=dict(scan_results[0].scan_params),
        timestamp=scan_results[0].timestamp,
        mpm_range=0,
    )


def calculate_il(reference: ScanResult, measurement: ScanResult) -> np.ndarray:
    """Calculate insertion loss from reference and measurement scans.

    IL = P_ref - P_meas  (dB)

    If the wavelength grids differ, the measurement powers are interpolated
    onto the reference wavelength grid before subtraction.
    """
    if np.array_equal(reference.wavelengths, measurement.wavelengths):
        meas_powers = measurement.powers
    else:
        meas_powers = np.interp(
            reference.wavelengths, measurement.wavelengths, measurement.powers
        )

    return reference.powers - meas_powers
