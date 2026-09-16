"""Tests for Santec STS sweep parameter rules."""

from __future__ import annotations

import pytest

from santecpro.sweep_rules import (
    ALLOWED_STEP_PM,
    get_allowed_speeds_nm_s,
    validate_sts_sweep_params,
)


def test_allowed_steps_match_santec_software_choices():
    assert ALLOWED_STEP_PM == (0.05, 0.1, 1, 5, 10, 20, 40, 50, 80, 100, 200, 500)


@pytest.mark.parametrize("step_nm", [0.001, 0.005, 0.01, 0.02, 0.04, 0.05, 0.08, 0.1, 0.2, 0.5])
def test_one_pm_and_larger_steps_allow_full_speed_table(step_nm):
    assert get_allowed_speeds_nm_s(step_nm) == (1, 5, 10, 20, 40, 50, 80, 100)


@pytest.mark.parametrize("step_nm", [0.00005, 0.0001])
def test_sub_pm_steps_allow_only_one_nm_per_second(step_nm):
    assert get_allowed_speeds_nm_s(step_nm) == (1,)


def test_validate_accepts_005_pm_step_with_one_nm_range_at_one_nm_per_second():
    validate_sts_sweep_params(start_wl=1540, stop_wl=1541, step=0.00005, speed=1)


def test_validate_rejects_005_pm_step_above_one_nm_range():
    with pytest.raises(ValueError, match="0.05 pm.*range <= 1 nm"):
        validate_sts_sweep_params(start_wl=1540, stop_wl=1541.001, step=0.00005, speed=1)


def test_validate_accepts_01_pm_step_with_ten_nm_range_at_one_nm_per_second():
    validate_sts_sweep_params(start_wl=1540, stop_wl=1550, step=0.0001, speed=1)


def test_validate_rejects_01_pm_step_above_ten_nm_range():
    with pytest.raises(ValueError, match="0.1 pm.*range <= 10 nm"):
        validate_sts_sweep_params(start_wl=1540, stop_wl=1550.001, step=0.0001, speed=1)


def test_validate_rejects_sub_pm_speed_other_than_one_nm_per_second():
    with pytest.raises(ValueError, match="speed must be 1 nm/s"):
        validate_sts_sweep_params(start_wl=1540, stop_wl=1541, step=0.0001, speed=5)


def test_validate_rejects_unsupported_step():
    with pytest.raises(ValueError, match="Unsupported sweep step"):
        validate_sts_sweep_params(start_wl=1540, stop_wl=1541, step=0.003, speed=1)


def test_validate_rejects_unsupported_speed_for_one_pm_and_larger_steps():
    with pytest.raises(ValueError, match="Unsupported sweep speed"):
        validate_sts_sweep_params(start_wl=1540, stop_wl=1541, step=0.001, speed=2)


@pytest.mark.parametrize('start,stop', [(float('nan'),1550), (1550,float('inf')), (1550,1550), (-1,1550)])
def test_rejects_invalid_endpoints(start, stop):
    with pytest.raises(ValueError):
        validate_sts_sweep_params(start, stop, .01, 1)
