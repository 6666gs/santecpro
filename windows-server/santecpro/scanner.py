"""Scanner module for coordinating wavelength scans between TSL and MPM."""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import numpy as np

from santecpro.instruments.mpm import MPM_RANGES
from santecpro.instruments.tsl import (
    SWEEP_MODE_CONT_ONE_WAY,
    SWEEP_STATUS_TRIGGER_STANDBY,
    TRIG_OUT_STEP,
)
from santecpro.instruments.mpm import MEAS_MODE_SWEEP1
from santecpro.sweep_rules import validate_sts_sweep_params

if TYPE_CHECKING:
    from santecpro.instruments.tsl import TSLInstrument
    from santecpro.instruments.mpm import MPMInstrument

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 1.0


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

    IL = P_meas - P_ref  (dB)

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

    return meas_powers - reference.powers


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
        sweep_mode: int = SWEEP_MODE_CONT_ONE_WAY,
        ranges: list[int] | None = None,
        mpm_channel: int = 1,
        mpm_module: int = 1,
        mpm_averaging_time_ms: float = 0.01,
    ) -> None:
        """Store scan parameters and configure both instruments.

        Args:
            start_wl: Start wavelength in nm.
            stop_wl: Stop wavelength in nm.
            step: Wavelength step in nm.
            speed: Sweep speed in nm/s.
            power: Output power in dBm.
            sweep_mode: TSL sweep mode number (0-3). Use constants from
                ``santecpro.instruments.tsl`` (e.g. ``SWEEP_MODE_CONT_ONE_WAY``).
            ranges: Optional list of MPM range numbers for multi-range scans.
            mpm_channel: MPM channel to read (1-based).
            mpm_module: MPM module to read (1-based).
            mpm_averaging_time_ms: MPM integration time in ms. This must be
                comfortably shorter than ``step / speed`` to avoid missing
                external trigger pulses.
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
            "mpm_averaging_time_ms": mpm_averaging_time_ms,
        }
        validate_sts_sweep_params(start_wl, stop_wl, step, speed)

        self._mpm.stop_logging()
        self._warn_mpm_error_state("before configure")

        # Configure TSL
        self._tsl.set_power(power)
        self._tsl.set_sweep_mode(sweep_mode)
        self._tsl.configure_sweep(start_wl, stop_wl, step, speed)
        self._verify_tsl_sweep_configuration(start_wl, stop_wl, step, speed, sweep_mode)
        self._tsl.set_trigger_output(TRIG_OUT_STEP)
        self._tsl.set_trigger_step_width(step)
        actual_trigger_step = self._tsl.get_trigger_step_width()
        if not np.isclose(actual_trigger_step, step, rtol=0.0, atol=1e-6):
            raise RuntimeError(
                f"TSL trigger step mismatch: requested {step:.6f} nm, "
                f"instrument reports {actual_trigger_step:.6f} nm"
            )
        self._tsl.set_scan_start_mode(1)  # 1 = wait for software trigger

        # Configure MPM
        self._mpm.set_unit(0)  # 0 = dBm
        self._mpm.set_range_mode(0)  # 0 = Manual
        self._mpm.set_measurement_mode(MEAS_MODE_SWEEP1)
        self._mpm.set_sweep_wavelength(start_wl, stop_wl, step)
        self._mpm.set_sweep_speed(speed)
        self._mpm.set_averaging_time(mpm_averaging_time_ms)
        expected_points = self._expected_points(start_wl, stop_wl, step)
        actual_points = self._mpm.get_logging_data_points()
        if actual_points != expected_points:
            raise RuntimeError(
                f"MPM LOGN mismatch: expected {expected_points}, instrument reports {actual_points}"
            )
        # SWEEP1 mode: LOGN is auto-calculated from WSET, no need to set manually

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

        self._mpm.stop_logging()
        self._warn_mpm_error_state("before scan")

        # Prepare MPM
        self._mpm.set_range(mpm_range)
        self._mpm.set_trigger_input(1)  # 1 = External trigger
        logger.info("MPM range=%d, trigger=external", mpm_range)

        # Put the TSL into trigger standby before arming the MPM. The actual
        # sweep is released by one software trigger after the MPM is ready.
        self._tsl.start_sweep()
        self._wait_for_tsl_status(SWEEP_STATUS_TRIGGER_STANDBY, timeout=5.0)

        self._mpm.start_logging()
        logger.info("MPM MEAS sent, waiting for hardware arm...")
        time.sleep(0.3)

        try:
            self._tsl.soft_trigger()
            logger.info("TSL sweep released by software trigger")

            # Do not poll the MPM during the sweep; GPIB traffic to the power meter
            # can disturb time-critical external-trigger logging on some setups.
            self._wait_for_expected_sweep()
            self._poll_mpm_logging(timeout=30.0)
        finally:
            self._stop_instruments_after_scan()

        # Retrieve data
        powers_list = self._mpm.get_channel_logging_data(mod, ch)
        powers = np.array(powers_list, dtype=float)

        wavelengths = np.linspace(
            self._config["start_wl"], self._config["stop_wl"], len(powers)
        )
        try:
            monitor_list = self._tsl.get_power_monitor_data()
            monitor_powers = np.array(monitor_list, dtype=float)
            if len(monitor_powers) != len(powers):
                logger.warning(
                    "TSL monitor length mismatch: got %d, expected %d; filling with NaN",
                    len(monitor_powers),
                    len(powers),
                )
                monitor_powers = np.full(len(powers), np.nan)
        except Exception as exc:
            logger.warning("Could not read TSL monitor data; filling with NaN: %s", exc)
            monitor_powers = np.full(len(powers), np.nan)

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
        mod = self._config.get("mpm_module", 1)
        if mpm_range is None:
            powers = self._mpm.get_power(mod)
            current_power = powers[ch - 1]
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
        poll_count = 0
        while True:
            status, count = self._mpm.get_logging_status()
            poll_count += 1
            if poll_count <= 5 or poll_count % 5 == 0:
                logger.info("MPM STAT? → status=%d, count=%d", status, count)
            if status == 1:  # COMPLETED
                logger.info("MPM measurement complete: %d data points", count)
                expected = None
                if {"start_wl", "stop_wl", "step"} <= self._config.keys():
                    expected = self._expected_points(
                        self._config["start_wl"],
                        self._config["stop_wl"],
                        self._config["step"],
                    )
                if expected is not None and count != expected:
                    raise RuntimeError(
                        f"MPM completed with {count} data points, expected {expected}. "
                        "This means trigger pulses were missed; reduce sweep speed or "
                        "increase wavelength step."
                    )
                return
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"MPM logging did not complete within {timeout}s "
                    f"(last status={status}, count={count})"
                )
            time.sleep(_POLL_INTERVAL)

    def _expected_sweep_wait(self) -> float:
        """Return a conservative scan wait time in seconds."""
        start = self._config["start_wl"]
        stop = self._config["stop_wl"]
        speed = self._config["speed"]
        return abs(stop - start) / speed + 2.0

    def _wait_for_expected_sweep(self) -> None:
        """Wait through the expected sweep duration while logging progress."""
        wait_s = self._expected_sweep_wait()
        logger.info("Waiting %.1fs for TSL sweep to finish before polling MPM", wait_s)
        deadline = time.monotonic() + wait_s
        next_log = time.monotonic() + 5.0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(1.0, remaining))
            now = time.monotonic()
            if now >= next_log:
                logger.info("Sweep wait in progress: %.1fs remaining", max(0.0, deadline - now))
                next_log = now + 5.0

    @staticmethod
    def _expected_points(start: float, stop: float, step: float) -> int:
        return int(round(abs(stop - start) / step)) + 1

    def _verify_tsl_sweep_configuration(
        self,
        start_wl: float,
        stop_wl: float,
        step: float,
        speed: float,
        sweep_mode: int,
    ) -> None:
        """Read back TSL sweep settings and fail if the instrument rejected them."""
        actual_mode = self._tsl.get_sweep_mode()
        actual_start = self._tsl.get_sweep_start()
        actual_stop = self._tsl.get_sweep_stop()
        actual_step = self._tsl.get_sweep_step()
        actual_speed = self._tsl.get_sweep_speed()
        logger.info(
            "TSL readback: mode=%s, start=%.6f nm, stop=%.6f nm, step=%.6f nm, speed=%.3f nm/s",
            actual_mode,
            actual_start,
            actual_stop,
            actual_step,
            actual_speed,
        )
        if actual_mode != sweep_mode:
            raise RuntimeError(
                f"TSL sweep mode mismatch: requested {sweep_mode}, instrument reports {actual_mode}"
            )
        if not np.isclose(actual_start, start_wl, rtol=0.0, atol=5e-7):
            raise RuntimeError(
                f"TSL sweep start mismatch: requested {start_wl:.6f} nm, "
                f"instrument reports {actual_start:.6f} nm"
            )
        if not np.isclose(actual_stop, stop_wl, rtol=0.0, atol=5e-7):
            raise RuntimeError(
                f"TSL sweep stop mismatch: requested {stop_wl:.6f} nm, "
                f"instrument reports {actual_stop:.6f} nm"
            )
        if not np.isclose(actual_step, step, rtol=0.0, atol=5e-7):
            raise RuntimeError(
                f"TSL sweep step mismatch: requested {step:.6f} nm, "
                f"instrument reports {actual_step:.6f} nm"
            )
        if not np.isclose(actual_speed, speed, rtol=0.0, atol=1e-3):
            raise RuntimeError(
                f"TSL sweep speed mismatch: requested {speed:.3f} nm/s, "
                f"instrument reports {actual_speed:.3f} nm/s"
            )

    def _warn_mpm_error_state(self, context: str) -> None:
        """Log the MPM error state without using it as a pre-scan interlock."""
        try:
            code, message = self._mpm.get_error()
        except Exception as exc:
            logger.warning("Could not query MPM ERR? %s: %s", context, exc)
            return
        if code != 0:
            logger.warning("MPM ERR? %s returned %d,%s", context, code, message)

    def _stop_instruments_after_scan(self) -> None:
        """Best-effort cleanup so failed scans do not leave devices armed."""
        for name, stop in (
            ("MPM logging", self._mpm.stop_logging),
            ("TSL sweep", self._tsl.stop_sweep),
        ):
            try:
                stop()
                logger.info("Stopped %s", name)
            except Exception as exc:
                logger.warning("Could not stop %s: %s", name, exc)

    def _wait_for_tsl_status(self, expected_status: int, timeout: float) -> None:
        """Poll TSL sweep status until it reaches ``expected_status``."""
        deadline = time.monotonic() + timeout
        last_status = None
        while True:
            last_status = self._tsl.get_sweep_status()
            if str(last_status).strip().startswith(str(expected_status)):
                return
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"TSL did not reach sweep status {expected_status} "
                    f"within {timeout}s (last status={last_status})"
                )
            time.sleep(0.1)
