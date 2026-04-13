"""Tests for the scanner module (data classes, algorithms, Scanner coordinator)."""

from __future__ import annotations

import numpy as np
import pytest
from unittest.mock import MagicMock, patch, call

from santecpro.instruments.tsl import TSLInstrument
from santecpro.instruments.mpm import MPMInstrument, MPM_RANGES
from santecpro.scanner import (
    ScanResult,
    ILMeasurement,
    merge_multi_range,
    calculate_il,
    Scanner,
    _POLL_INTERVAL,
)


# ======================================================================
# Helper factories
# ======================================================================


def _make_scan_result(
    start_wl: float = 1500.0,
    stop_wl: float = 1510.0,
    n: int = 11,
    powers: np.ndarray | None = None,
    monitor_powers: np.ndarray | None = None,
    mpm_range: int = 1,
) -> ScanResult:
    """Build a ScanResult with sensible defaults for testing."""
    wavelengths = np.linspace(start_wl, stop_wl, n)
    if powers is None:
        powers = np.full(n, -10.0)
    if monitor_powers is None:
        monitor_powers = np.full(n, 7.5)
    return ScanResult(
        wavelengths=wavelengths,
        powers=powers,
        monitor_powers=monitor_powers,
        scan_params={"start_wl": start_wl, "stop_wl": stop_wl, "step": 1.0},
        timestamp="2026-04-13T00:00:00+00:00",
        mpm_range=mpm_range,
    )


def _make_mock_tsl():
    tsl = MagicMock(spec=TSLInstrument)
    tsl.is_connected = True
    tsl.idn = "SANTEC,TSL-550,12345,1.00"
    tsl.get_sweep_status.return_value = "STANDING_BY_TRIGGER"
    tsl.get_logging_data_points.return_value = 5
    tsl.get_power_monitor_data.return_value = [7.5, 7.6, 7.7, 7.8, 7.9]
    return tsl


def _make_mock_mpm():
    mpm = MagicMock(spec=MPMInstrument)
    mpm.is_connected = True
    mpm.idn = "SANTEC,MPM-210,67890,1.16"
    mpm.get_logging_status.return_value = (1, 5)
    mpm.get_channel_logging_data.return_value = [-10.0, -11.0, -12.0, -13.0, -14.0]
    mpm.get_power.return_value = -10.0
    return mpm


# ======================================================================
# Pure algorithm tests -- merge_multi_range
# ======================================================================


class TestMergeMultiRange:
    """Tests for the merge_multi_range algorithm."""

    def test_single_range_passes_through(self):
        """A single ScanResult should be returned unchanged (copies made)."""
        sr = _make_scan_result(
            powers=np.array([-10.0, -15.0, -20.0]),
            n=3,
            mpm_range=1,
        )
        merged = merge_multi_range([sr])

        np.testing.assert_array_equal(merged.powers, sr.powers)
        np.testing.assert_array_equal(merged.wavelengths, sr.wavelengths)
        np.testing.assert_array_equal(merged.monitor_powers, sr.monitor_powers)
        assert merged.mpm_range == 1

    def test_two_ranges_overlap_picks_best(self):
        """When both ranges are valid at a point, prefer lowest range number."""
        wl = np.array([1500.0, 1505.0, 1510.0])

        # Range 1 valid range: -30..+10 dBm
        # Both powers (-5, -5) are within range 1.
        sr1 = _make_scan_result(
            powers=np.array([-5.0, -5.0, -5.0]),
            monitor_powers=np.array([7.5, 7.5, 7.5]),
            n=3,
            mpm_range=1,
        )
        sr1.wavelengths = wl

        # Range 3 valid range: -50..-10 dBm
        # Only the middle point (-25) is valid for range 3, but range 1 covers all.
        sr3 = _make_scan_result(
            powers=np.array([-5.0, -25.0, -5.0]),
            monitor_powers=np.array([7.0, 7.0, 7.0]),
            n=3,
            mpm_range=3,
        )
        sr3.wavelengths = wl

        merged = merge_multi_range([sr3, sr1])  # order shouldn't matter
        # All points should use range 1 data since it has the lowest range number
        np.testing.assert_array_almost_equal(merged.powers, [-5.0, -5.0, -5.0])
        np.testing.assert_array_almost_equal(merged.monitor_powers, [7.5, 7.5, 7.5])

    def test_two_ranges_stitch_together(self):
        """Some points from range 1, some from range 3."""
        wl = np.array([1500.0, 1505.0, 1510.0])

        # Range 1: -30..+10. Powers: -5 (valid), -35 (INVALID), -5 (valid)
        sr1 = _make_scan_result(
            powers=np.array([-5.0, -35.0, -5.0]),
            monitor_powers=np.array([7.5, 7.5, 7.5]),
            n=3,
            mpm_range=1,
        )
        sr1.wavelengths = wl

        # Range 3: -50..-10. Powers: -5 (valid but range 1 wins), -25 (valid), -5 (valid but range 1 wins)
        sr3 = _make_scan_result(
            powers=np.array([-5.0, -25.0, -5.0]),
            monitor_powers=np.array([7.0, 7.0, 7.0]),
            n=3,
            mpm_range=3,
        )
        sr3.wavelengths = wl

        merged = merge_multi_range([sr1, sr3])
        # Point 0: range 1 valid -> -5
        # Point 1: range 1 invalid, range 3 valid -> -25
        # Point 2: range 1 valid -> -5
        np.testing.assert_array_almost_equal(merged.powers, [-5.0, -25.0, -5.0])
        # Monitor powers should follow the same selection
        np.testing.assert_array_almost_equal(merged.monitor_powers, [7.5, 7.0, 7.5])

    def test_gap_produces_nan(self):
        """A point with no valid range should be NaN."""
        wl = np.array([1500.0, 1505.0, 1510.0])

        # Range 1: -30..+10. Powers: -5 (valid), -45 (INVALID), -5 (valid)
        sr1 = _make_scan_result(
            powers=np.array([-5.0, -45.0, -5.0]),
            monitor_powers=np.array([7.5, 7.5, 7.5]),
            n=3,
            mpm_range=1,
        )
        sr1.wavelengths = wl

        # Range 3: -50..-10. Powers: -5 (INVALID for range 3), -25 (valid), -5 (INVALID)
        # At point 0: -5 > -10 so outside range 3 -> NaN stays
        # At point 1: -25 is in [-50, -10] -> valid, fills the gap from range 1
        # At point 2: -5 > -10 so outside range 3 -> NaN stays
        sr3 = _make_scan_result(
            powers=np.array([-5.0, -25.0, -5.0]),
            monitor_powers=np.array([7.0, 7.0, 7.0]),
            n=3,
            mpm_range=3,
        )
        sr3.wavelengths = wl

        merged = merge_multi_range([sr1, sr3])
        # Point 0: range 1 valid -> -5
        # Point 1: range 1 invalid, range 3 valid -> -25
        # Point 2: range 1 valid -> -5
        np.testing.assert_array_almost_equal(merged.powers, [-5.0, -25.0, -5.0])

        # True gap test: a point that falls outside ALL provided ranges.
        wl2 = np.array([1500.0, 1505.0, 1510.0])
        # Range 3: -50..-10, power -5 is INVALID for range 3 (-5 > -10)
        sr_c = _make_scan_result(
            powers=np.array([-5.0, -5.0, -5.0]),
            n=3,
            mpm_range=3,
        )
        sr_c.wavelengths = wl2

        # Range 5: -80..-30, power -5 is INVALID for range 5 (-5 > -30)
        sr_d = _make_scan_result(
            powers=np.array([-5.0, -5.0, -5.0]),
            n=3,
            mpm_range=5,
        )
        sr_d.wavelengths = wl2

        merged2 = merge_multi_range([sr_c, sr_d])
        assert np.all(np.isnan(merged2.powers))

    def test_merged_uses_first_wavelength_grid(self):
        """The merged result uses the wavelength grid of the first ScanResult."""
        wl_a = np.array([1500.0, 1502.0, 1504.0, 1506.0, 1508.0, 1510.0])
        wl_b = np.array([1500.0, 1505.0, 1510.0])

        sr1 = _make_scan_result(
            powers=np.full(6, -5.0),
            monitor_powers=np.full(6, 7.5),
            n=6,
            mpm_range=1,
        )
        sr1.wavelengths = wl_a

        sr2 = _make_scan_result(
            powers=np.full(3, -25.0),
            monitor_powers=np.full(3, 7.0),
            n=3,
            mpm_range=3,
        )
        sr2.wavelengths = wl_b

        merged = merge_multi_range([sr1, sr2])
        np.testing.assert_array_equal(merged.wavelengths, wl_a)
        assert len(merged.powers) == len(wl_a)

    def test_empty_raises(self):
        """merge_multi_range with empty list should raise ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            merge_multi_range([])


# ======================================================================
# Pure algorithm tests -- calculate_il
# ======================================================================


class TestCalculateIL:
    """Tests for the calculate_il algorithm."""

    def test_basic_il(self):
        """IL = P_ref - P_meas."""
        ref = _make_scan_result(powers=np.array([0.0, -1.0, -2.0]), n=3)
        meas = _make_scan_result(powers=np.array([-3.0, -4.0, -5.0]), n=3)

        il = calculate_il(ref, meas)
        np.testing.assert_array_almost_equal(il, [3.0, 3.0, 3.0])

    def test_il_with_monitor_subtraction(self):
        """Verify IL computation is purely ref_power - meas_power."""
        ref = _make_scan_result(
            powers=np.array([-5.0, -5.0, -5.0]),
            monitor_powers=np.array([7.5, 7.5, 7.5]),
            n=3,
        )
        meas = _make_scan_result(
            powers=np.array([-10.0, -11.0, -12.0]),
            monitor_powers=np.array([7.5, 7.5, 7.5]),
            n=3,
        )

        il = calculate_il(ref, meas)
        np.testing.assert_array_almost_equal(il, [5.0, 6.0, 7.0])

    def test_il_with_different_wavelength_grids_interpolates(self):
        """When grids differ, measurement is interpolated onto reference grid."""
        ref_wl = np.array([1500.0, 1505.0, 1510.0])
        ref = _make_scan_result(
            powers=np.array([0.0, 0.0, 0.0]),
            n=3,
        )
        ref.wavelengths = ref_wl

        meas_wl = np.array([1500.0, 1502.5, 1505.0, 1507.5, 1510.0])
        meas = _make_scan_result(
            powers=np.array([0.0, -1.0, -2.0, -3.0, -4.0]),
            n=5,
        )
        meas.wavelengths = meas_wl

        il = calculate_il(ref, meas)
        # meas interpolated at 1500, 1505, 1510 -> 0, -2, -4
        # IL = 0-0, 0-(-2), 0-(-4) = 0, 2, 4
        np.testing.assert_array_almost_equal(il, [0.0, 2.0, 4.0])


# ======================================================================
# Scanner class tests
# ======================================================================


class TestScannerConfigure:
    """Tests for Scanner.configure."""

    def test_configure_stores_params(self):
        tsl, mpm = _make_mock_tsl(), _make_mock_mpm()
        scanner = Scanner(tsl, mpm)

        scanner.configure(
            start_wl=1500,
            stop_wl=1600,
            step=0.01,
            speed=50,
            power=0,
            sweep_mode="CONTINUOUS_ONE_WAY",
            ranges=[1, 3],
            mpm_channel=2,
            mpm_module=1,
        )

        assert scanner._config["start_wl"] == 1500
        assert scanner._config["stop_wl"] == 1600
        assert scanner._config["step"] == 0.01
        assert scanner._config["speed"] == 50
        assert scanner._config["power"] == 0
        assert scanner._config["ranges"] == [1, 3]
        assert scanner._config["mpm_channel"] == 2

    def test_configure_calls_tsl(self):
        tsl, mpm = _make_mock_tsl(), _make_mock_mpm()
        scanner = Scanner(tsl, mpm)
        scanner.configure(
            start_wl=1500, stop_wl=1600, step=1, speed=50, power=-5
        )

        tsl.set_power.assert_called_once_with(-5)
        tsl.configure_sweep.assert_called_once_with(1500, 1600, 1, 50)
        tsl.set_trigger_output.assert_called_once_with("STEP")

    def test_configure_calls_mpm(self):
        tsl, mpm = _make_mock_tsl(), _make_mock_mpm()
        scanner = Scanner(tsl, mpm)
        scanner.configure(
            start_wl=1500, stop_wl=1600, step=1, speed=50, power=-5
        )

        mpm.set_unit.assert_called_once_with("dBm")
        mpm.set_range_mode.assert_called_once_with("MANUAL")
        # data_points = (1600-1500)/1 + 1 = 101
        mpm.set_logging_data_points.assert_called_once_with(101)


class TestScannerSingleScan:
    """Tests for Scanner.run_single_scan."""

    def _configured_scanner(self):
        tsl, mpm = _make_mock_tsl(), _make_mock_mpm()
        scanner = Scanner(tsl, mpm)
        scanner.configure(
            start_wl=1500, stop_wl=1504, step=1, speed=50, power=0
        )
        return scanner, tsl, mpm

    def test_single_scan_returns_scan_result(self):
        scanner, tsl, mpm = self._configured_scanner()
        result = scanner.run_single_scan(mpm_range=2, plot=False, save_csv=None)

        assert isinstance(result, ScanResult)
        assert len(result.powers) == 5
        assert len(result.wavelengths) == 5
        assert result.mpm_range == 2
        np.testing.assert_array_almost_equal(
            result.powers, [-10.0, -11.0, -12.0, -13.0, -14.0]
        )
        np.testing.assert_array_almost_equal(
            result.monitor_powers, [7.5, 7.6, 7.7, 7.8, 7.9]
        )
        np.testing.assert_array_almost_equal(
            result.wavelengths, [1500.0, 1501.0, 1502.0, 1503.0, 1504.0]
        )

    def test_single_scan_sequence(self):
        """Verify the TSL/MPM call order during a single scan."""
        scanner, tsl, mpm = self._configured_scanner()

        # Track call order
        call_order = []

        def record(name):
            def wrapper(*args, **kwargs):
                call_order.append(name)
            return wrapper

        mpm.set_range.side_effect = record("mpm.set_range")
        mpm.set_measurement_mode.side_effect = record("mpm.set_measurement_mode")
        mpm.set_trigger_input.side_effect = record("mpm.set_trigger_input")
        tsl.set_scan_start_mode.side_effect = record("tsl.set_scan_start_mode")
        mpm.start_logging.side_effect = record("mpm.start_logging")
        tsl.start_sweep.side_effect = record("tsl.start_sweep")
        tsl.soft_trigger.side_effect = record("tsl.soft_trigger")
        mpm.stop_logging.side_effect = record("mpm.stop_logging")
        tsl.stop_sweep.side_effect = record("tsl.stop_sweep")

        scanner.run_single_scan(mpm_range=2, plot=False, save_csv=None)

        # Verify key ordering constraints
        assert call_order.index("mpm.set_range") < call_order.index("mpm.start_logging")
        assert call_order.index("tsl.set_scan_start_mode") < call_order.index("tsl.start_sweep")
        assert call_order.index("mpm.start_logging") < call_order.index("tsl.start_sweep")
        assert call_order.index("tsl.start_sweep") < call_order.index("tsl.soft_trigger")
        assert call_order.index("tsl.soft_trigger") < call_order.index("mpm.stop_logging")

        # Verify specific calls
        mpm.set_range.assert_called_once_with(2)
        mpm.set_measurement_mode.assert_called_once_with("SWEEP1")
        mpm.set_trigger_input.assert_called_once_with("EXTERNAL")
        tsl.set_scan_start_mode.assert_called_once_with("WAITING_FOR_TRIGGER")


class TestScannerMultiRange:
    """Tests for multi-range scan methods."""

    def test_multi_range_runs_multiple_scans(self):
        tsl, mpm = _make_mock_tsl(), _make_mock_mpm()
        scanner = Scanner(tsl, mpm)
        scanner.configure(
            start_wl=1500, stop_wl=1504, step=1, speed=50, power=0
        )

        results = scanner.run_multi_range_scan(
            ranges=[1, 3], plot=False, save_raw_csv=None
        )

        assert len(results) == 2
        assert results[0].mpm_range == 1
        assert results[1].mpm_range == 3

    def test_multi_range_merge_called(self):
        """run_multi_range_scan_merged should return a merged ScanResult."""
        tsl, mpm = _make_mock_tsl(), _make_mock_mpm()
        scanner = Scanner(tsl, mpm)
        scanner.configure(
            start_wl=1500, stop_wl=1504, step=1, speed=50, power=0
        )

        # Patch merge_multi_range to verify it gets called
        with patch("santecpro.scanner.merge_multi_range") as mock_merge:
            # Configure the mock to return a plausible ScanResult
            mock_merge.return_value = ScanResult(
                wavelengths=np.linspace(1500, 1504, 5),
                powers=np.full(5, -10.0),
                monitor_powers=np.full(5, 7.5),
                mpm_range=0,
            )
            result = scanner.run_multi_range_scan_merged(
                ranges=[1, 3], plot=False, save_raw_csv=None
            )

            mock_merge.assert_called_once()
            assert result.mpm_range == 0


class TestScannerILMeasurement:
    """Tests for Scanner.run_il_measurement."""

    def test_run_il_measurement(self):
        """run_il_measurement returns an ILMeasurement with correct fields."""
        tsl, mpm = _make_mock_tsl(), _make_mock_mpm()
        scanner = Scanner(tsl, mpm)
        scanner.configure(
            start_wl=1500, stop_wl=1504, step=1, speed=50, power=0
        )

        il_result = scanner.run_il_measurement(
            ranges=[1], plot=False, save_raw_csv=None, save_loss_csv=None
        )

        assert isinstance(il_result, ILMeasurement)
        assert isinstance(il_result.reference, ScanResult)
        assert isinstance(il_result.measurement, ScanResult)
        assert isinstance(il_result.il, np.ndarray)
        assert isinstance(il_result.wavelengths, np.ndarray)

        # IL should be reference.power - measurement.power
        assert len(il_result.il) == len(il_result.wavelengths)
        assert len(il_result.il) == len(il_result.reference.powers)

        # Verify the auto-range was used: mpm.get_power was called for reference
        mpm.get_power.assert_called()
        mpm.select_optimal_range.assert_called_once_with(-10.0)


class TestScannerPolling:
    """Tests for the internal _poll_mpm_logging method."""

    def test_poll_completes_immediately(self):
        tsl, mpm = _make_mock_tsl(), _make_mock_mpm()
        scanner = Scanner(tsl, mpm)
        # Default mock returns (1, 5) i.e. COMPLETED
        scanner._poll_mpm_logging(timeout=1.0)
        mpm.get_logging_status.assert_called_once()

    def test_poll_retries_then_completes(self):
        tsl, mpm = _make_mock_tsl(), _make_mock_mpm()
        scanner = Scanner(tsl, mpm)

        # First two calls: still logging (0, 3). Third call: completed (1, 5).
        mpm.get_logging_status.side_effect = [(0, 3), (0, 4), (1, 5)]

        with patch("santecpro.scanner.time") as mock_time:
            mock_time.monotonic.side_effect = [0, 0.1, 0.2]
            mock_time.sleep.return_value = None
            scanner._poll_mpm_logging(timeout=10.0)

        assert mpm.get_logging_status.call_count == 3

    def test_poll_raises_timeout(self):
        tsl, mpm = _make_mock_tsl(), _make_mock_mpm()
        scanner = Scanner(tsl, mpm)

        # Always return "logging" status
        mpm.get_logging_status.return_value = (0, 3)

        with patch("santecpro.scanner.time") as mock_time:
            # Simulate time progressing past deadline
            mock_time.monotonic.side_effect = [0, 5.0, 10.0, 300.1]
            mock_time.sleep.return_value = None

            with pytest.raises(TimeoutError, match="did not complete"):
                scanner._poll_mpm_logging(timeout=300.0)
