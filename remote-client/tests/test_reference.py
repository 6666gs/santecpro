"""Tests for reference-based insertion-loss calculations."""

from __future__ import annotations

import numpy as np
import pytest

from santecpro.reference import calculate_reference_il, calculate_reference_il_for_channel
from santecpro.results import ScanResult


def _result(wavelengths, powers):
    return ScanResult(
        wavelengths=np.array(wavelengths, dtype=float),
        powers=np.array(powers, dtype=float),
        monitor_powers=np.zeros(len(wavelengths), dtype=float),
    )


def test_calculate_reference_il_interpolates_reference_to_measurement_grid():
    reference = _result([1540.0, 1541.0, 1542.0], [0.0, 1.0, 2.0])
    measurement = _result([1540.5, 1541.5], [-10.0, -20.0])

    il = calculate_reference_il(reference, measurement)

    np.testing.assert_allclose(il.wavelengths, [1540.5, 1541.5])
    np.testing.assert_allclose(il.reference_powers, [0.5, 1.5])
    np.testing.assert_allclose(il.il, [-10.5, -21.5])


def test_calculate_reference_il_rejects_measurement_outside_reference_span():
    reference = _result([1540.0, 1541.0], [0.0, 1.0])
    measurement = _result([1539.9, 1540.5], [-10.0, -20.0])

    with pytest.raises(ValueError, match="outside reference wavelength span"):
        calculate_reference_il(reference, measurement)


def test_calculate_reference_il_for_channel_uses_matching_channel():
    reference = _result([1540.0, 1541.0], [0.0, 0.0])
    reference.channel_powers = {
        1: np.array([0.0, 1.0]),
        2: np.array([10.0, 12.0]),
    }
    measurement = _result([1540.5], [-20.0])
    measurement.channel_powers = {
        1: np.array([-20.0]),
        2: np.array([7.0]),
    }

    il = calculate_reference_il_for_channel(reference, measurement, 2)

    np.testing.assert_allclose(il.reference_powers, [11.0])
    np.testing.assert_allclose(il.il, [-4.0])
