"""Scanner module for coordinating wavelength scans between TSL and MPM."""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import numpy as np

from santecpro.instruments.mpm import MPM_RANGES

if TYPE_CHECKING:
    from santecpro.instruments.tsl import TSLInstrument
    from santecpro.instruments.mpm import MPMInstrument

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 0.2


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Pure algorithm functions
# ---------------------------------------------------------------------------


def merge_multi_range(scan_results: list[ScanResult]) -> ScanResult:
    """Merge multi-range scan data into a single ScanResult.

    For each wavelength point, select the power reading from the range where
    the signal falls within the valid dynamic range.  When multiple ranges
    cover a point, prefer the *lowest* range number (best SNR).  Wavelength
    points with no valid range are filled with NaN.

    The output wavelength grid is taken from the first ScanResult.

    Args:
        scan_results: List of ScanResult objects, one per MPM range.

    Returns:
        A merged ScanResult with ``mpm_range`` set to 0 to indicate a
        multi-range merge.
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

    # Use the wavelength grid from the first result as the reference grid.
    ref_wl = scan_results[0].wavelengths
    n = len(ref_wl)
    merged_powers = np.full(n, np.nan)
    merged_monitor = np.full(n, np.nan)

    # Sort results by range number (ascending) so that lowest range wins.
    sorted_results = sorted(scan_results, key=lambda sr: sr.mpm_range)

    # Build a map: range_number -> (powers_on_ref_grid, monitor_on_ref_grid)
    for sr in sorted_results:
        rng = sr.mpm_range
        min_p, max_p = MPM_RANGES[rng]

        if np.array_equal(sr.wavelengths, ref_wl):
            pows = sr.powers.copy()
            mons = sr.monitor_powers.copy()
        else:
            pows = np.interp(ref_wl, sr.wavelengths, sr.powers)
            mons = np.interp(ref_wl, sr.wavelengths, sr.monitor_powers)

        # Mask: True where the power is within the valid dynamic range.
        valid = (pows >= min_p) & (pows <= max_p)

        # Only fill positions that are still NaN (so lowest range has priority).
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

    Args:
        reference: Reference (no-DUT) ScanResult.
        measurement: Measurement (with-DUT) ScanResult.

    Returns:
        Array of IL values in dB, same length as reference.wavelengths.
    """
    if np.array_equal(reference.wavelengths, measurement.wavelengths):
        meas_powers = measurement.powers
    else:
        meas_powers = np.interp(
            reference.wavelengths, measurement.wavelengths, measurement.powers
        )

    return reference.powers - meas_powers


# ---------------------------------------------------------------------------
# Scanner coordinator class
# ---------------------------------------------------------------------------


class Scanner:
    """Coordinates wavelength scanning between a TSL laser and an MPM power meter.

    Typical workflow::

        scanner = Scanner(tsl, mpm)
        scanner.configure(start_wl=1500, stop_wl=1600, step=0.01,
                          speed=50, power=0)
        result = scanner.run_single_scan(mpm_range=2)

    For multi-range scans::

        merged = scanner.run_multi_range_scan_merged(ranges=[1, 3, 5])

    For insertion-loss measurements::

        il_result = scanner.run_il_measurement(ranges=[1, 3, 5])
    """

    def __init__(self, tsl: "TSLInstrument", mpm: "MPMInstrument") -> None:
        self._tsl = tsl
        self._mpm = mpm
        self._config: dict = {}

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(
        self,
        start_wl: float,
        stop_wl: float,
        step: float,
        speed: float,
        power: float,
        sweep_mode: str = "CONTINUOUS_ONE_WAY",
        ranges: list[int] | None = None,
        mpm_channel: int = 1,
        mpm_module: int = 1,
    ) -> None:
        """Store scan parameters and configure both instruments.

        Args:
            start_wl: Start wavelength in nm.
            stop_wl: Stop wavelength in nm.
            step: Wavelength step in nm.
            speed: Sweep speed in nm/s.
            power: Output power in dBm.
            sweep_mode: TSL sweep mode string.
            ranges: Optional list of MPM range numbers for multi-range scans.
            mpm_channel: MPM channel to read (1-based).
            mpm_module: MPM module to read (1-based).
        """
        self._config = {
            "start_wl": start_wl,
            "stop_wl": stop_wl,
            "step": step,
            "speed": speed,
            "power": power,
            "sweep_mode": sweep_mode,
            "ranges": ranges or [1],
            "mpm_channel": mpm_channel,
            "mpm_module": mpm_module,
        }

        # Configure TSL
        self._tsl.set_power(power)
        self._tsl.set_sweep_mode(sweep_mode)
        self._tsl.configure_sweep(start_wl, stop_wl, step, speed)
        self._tsl.set_trigger_output("STEP")

        # Configure MPM
        self._mpm.set_unit("dBm")
        self._mpm.set_range_mode("MANUAL")

        data_points = int(round((stop_wl - start_wl) / step)) + 1
        self._mpm.set_logging_data_points(data_points)

    # ------------------------------------------------------------------
    # Single-range scan
    # ------------------------------------------------------------------

    def run_single_scan(
        self,
        mpm_range: int = 1,
        plot: bool = True,
        save_csv: str | None = None,
    ) -> ScanResult:
        """Execute a single-range wavelength scan.

        Args:
            mpm_range: MPM dynamic range number (1-5).
            plot: If True, plot the result (requires santecpro.plotter).
            save_csv: If a file path is given, save raw CSV (requires
                santecpro.exporter).

        Returns:
            ScanResult with the scan data.
        """
        ch = self._config.get("mpm_channel", 1)
        mod = self._config.get("mpm_module", 1)

        # Prepare MPM
        self._mpm.set_range(mpm_range)
        self._mpm.set_measurement_mode("SWEEP1")
        self._mpm.set_trigger_input("EXTERNAL")

        # Prepare TSL
        self._tsl.set_scan_start_mode("WAITING_FOR_TRIGGER")

        # Start MPM logging first
        self._mpm.start_logging()

        # Start TSL sweep
        self._tsl.start_sweep()

        # Soft trigger to begin
        self._tsl.soft_trigger()

        # Poll MPM until logging completes
        self._poll_mpm_logging()

        # Stop logging and sweep
        self._mpm.stop_logging()
        self._tsl.stop_sweep()

        # Retrieve data
        powers_list = self._mpm.get_channel_logging_data(mod, ch)
        powers = np.array(powers_list, dtype=float)

        monitor_list = self._tsl.get_power_monitor_data()
        monitor_powers = np.array(monitor_list, dtype=float)

        wavelengths = np.linspace(
            self._config["start_wl"], self._config["stop_wl"], len(powers)
        )

        timestamp = datetime.now(timezone.utc).isoformat()

        result = ScanResult(
            wavelengths=wavelengths,
            powers=powers,
            monitor_powers=monitor_powers,
            scan_params=dict(self._config),
            timestamp=timestamp,
            mpm_range=mpm_range,
        )

        if plot:
            from santecpro.plotter import plot_scan_result

            plot_scan_result(result)

        if save_csv:
            from santecpro.exporter import save_raw_csv

            save_raw_csv(result, self._tsl.idn, self._mpm.idn, save_csv)

        return result

    # ------------------------------------------------------------------
    # Multi-range scans
    # ------------------------------------------------------------------

    def run_multi_range_scan(
        self,
        ranges: list[int] | None = None,
        plot: bool = True,
        save_raw_csv: str | None = None,
    ) -> list[ScanResult]:
        """Run a single-range scan for each specified MPM range.

        Args:
            ranges: List of MPM range numbers. Defaults to configured ranges.
            plot: If True, plot each result.
            save_raw_csv: If given, save CSV for each range.

        Returns:
            List of ScanResult objects, one per range.
        """
        ranges = ranges or self._config.get("ranges", [1])
        results: list[ScanResult] = []
        for rng in ranges:
            logger.info("Scanning with MPM range %d", rng)
            result = self.run_single_scan(
                mpm_range=rng,
                plot=plot,
                save_csv=save_raw_csv,
            )
            results.append(result)
        return results

    def run_multi_range_scan_merged(
        self,
        ranges: list[int] | None = None,
        plot: bool = True,
        save_raw_csv: str | None = None,
    ) -> ScanResult:
        """Run a multi-range scan and merge the results.

        Args:
            ranges: List of MPM range numbers.
            plot: If True, plot the merged result.
            save_raw_csv: If given, save CSV for each range.

        Returns:
            A merged ScanResult.
        """
        results = self.run_multi_range_scan(ranges=ranges, plot=plot, save_raw_csv=save_raw_csv)
        merged = merge_multi_range(results)

        if plot:
            from santecpro.plotter import plot_scan_result

            plot_scan_result(merged)

        return merged

    # ------------------------------------------------------------------
    # Reference / IL
    # ------------------------------------------------------------------

    def run_reference_scan(self, mpm_range: int | None = None) -> ScanResult:
        """Run a reference (no-DUT) scan.

        If ``mpm_range`` is None the optimal range is selected automatically
        using the current MPM power reading.

        Args:
            mpm_range: Explicit MPM range, or None for auto-selection.

        Returns:
            ScanResult for the reference scan.
        """
        ch = self._config.get("mpm_channel", 1)
        if mpm_range is None:
            current_power = self._mpm.get_power(ch)
            mpm_range = self._mpm.select_optimal_range(current_power)
        return self.run_single_scan(mpm_range=mpm_range, plot=False, save_csv=None)

    def run_il_measurement(
        self,
        ranges: list[int] | None = None,
        plot: bool = True,
        save_raw_csv: str | None = None,
        save_loss_csv: str | None = None,
    ) -> ILMeasurement:
        """Run a full insertion-loss measurement: reference + DUT measurement.

        Args:
            ranges: MPM ranges for the DUT measurement scan.
            plot: If True, plot the IL result.
            save_raw_csv: If given, save raw CSV for each range scan.
            save_loss_csv: If given, save IL CSV (requires santecpro.exporter).

        Returns:
            ILMeasurement with reference, measurement, IL, and wavelengths.
        """
        # Reference scan (auto-range)
        reference = self.run_reference_scan()

        # DUT measurement (multi-range, merged)
        measurement = self.run_multi_range_scan_merged(
            ranges=ranges,
            plot=plot,
            save_raw_csv=save_raw_csv,
        )

        il = calculate_il(reference, measurement)

        result = ILMeasurement(
            reference=reference,
            measurement=measurement,
            il=il,
            wavelengths=reference.wavelengths,
        )

        if save_loss_csv:
            from santecpro.exporter import save_loss_csv as _save_loss_csv

            _save_loss_csv(result, self._tsl.idn, self._mpm.idn, save_loss_csv)

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _poll_mpm_logging(self, timeout: float = 300.0) -> None:
        """Poll MPM logging status until it reports COMPLETED (status==1).

        Args:
            timeout: Maximum time to wait in seconds.

        Raises:
            TimeoutError: If the logging does not complete within *timeout*.
        """
        deadline = time.monotonic() + timeout
        while True:
            status, count = self._mpm.get_logging_status()
            if status == 1:  # COMPLETED
                return
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"MPM logging did not complete within {timeout}s "
                    f"(last status={status}, count={count})"
                )
            time.sleep(_POLL_INTERVAL)
