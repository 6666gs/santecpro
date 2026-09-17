"""Tests for santecpro.plotter."""

from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from santecpro.results import ScanResult, ILMeasurement
from santecpro.plotter import plot_scan_result, plot_il_result


def _make_scan_result() -> ScanResult:
    return ScanResult(
        wavelengths=np.array([1500.0, 1500.001, 1500.002]),
        powers=np.array([-33.268, -33.280, -33.275]),
        monitor_powers=np.array([7.58, 7.59, 7.60]),
        scan_params={
            "start_wl": 1500.0,
            "stop_wl": 1630.0,
            "step": 0.001,
            "speed": 20.0,
            "power": 0.0,
        },
        timestamp="2026-04-13T10:30:00",
        mpm_range=1,
    )


def _make_il_measurement() -> ILMeasurement:
    ref = _make_scan_result()
    meas = ScanResult(
        wavelengths=np.array([1500.0, 1500.001, 1500.002]),
        powers=np.array([-40.268, -40.280, -40.275]),
        monitor_powers=np.array([7.58, 7.59, 7.60]),
        scan_params={
            "start_wl": 1500.0,
            "stop_wl": 1630.0,
            "step": 0.001,
            "speed": 20.0,
            "power": 0.0,
        },
        timestamp="2026-04-13T10:30:00",
        mpm_range=1,
    )
    il = meas.powers - ref.powers
    return ILMeasurement(
        reference=ref,
        measurement=meas,
        il=il,
        wavelengths=ref.wavelengths,
    )


class TestPlotScanResult:
    @patch("santecpro.plotter.plt")
    def test_plot_creates_figure(self, mock_plt):
        """plot_scan_result should call subplots, plot, and show."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)

        scan = _make_scan_result()
        plot_scan_result(scan)

        mock_plt.subplots.assert_called_once_with(figsize=(10, 6))
        mock_ax.plot.assert_called_once()
        mock_plt.tight_layout.assert_called_once()
        mock_plt.show.assert_called_once()

    @patch("santecpro.plotter.plt")
    def test_plot_sets_labels(self, mock_plt):
        """plot_scan_result should set xlabel, ylabel, and title."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)

        scan = _make_scan_result()
        plot_scan_result(scan)

        mock_ax.set_xlabel.assert_called_once_with("Wavelength (nm)")
        mock_ax.set_ylabel.assert_called_once_with("Power (dBm)")
        mock_ax.set_title.assert_called_once()
        title_arg = mock_ax.set_title.call_args[0][0]
        assert "Scan Result" in title_arg


class TestPlotIlResult:
    @patch("santecpro.plotter.plt")
    def test_plot_il_creates_figure(self, mock_plt):
        """plot_il_result should call subplots, plot, and show."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)

        il_meas = _make_il_measurement()
        plot_il_result(il_meas)

        mock_plt.subplots.assert_called_once_with(figsize=(10, 6))
        mock_ax.plot.assert_called_once()
        mock_plt.tight_layout.assert_called_once()
        mock_plt.show.assert_called_once()

    @patch("santecpro.plotter.plt")
    def test_plot_il_title(self, mock_plt):
        """plot_il_result should set a title containing 'IL'."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)

        il_meas = _make_il_measurement()
        plot_il_result(il_meas)

        mock_ax.set_title.assert_called_once()
        title_arg = mock_ax.set_title.call_args[0][0]
        assert "IL" in title_arg
