"""Santec STS sweep parameter rules shared by local and Windows backends."""

from __future__ import annotations

import math


ALLOWED_STEP_PM = (0.05, 0.1, 1, 5, 10, 20, 40, 50, 80, 100, 200, 500)
ALLOWED_STEP_NM = tuple(step_pm / 1000 for step_pm in ALLOWED_STEP_PM)
FULL_SPEED_TABLE_NM_S = (1, 5, 10, 20, 40, 50, 80, 100)

_STEP_TOL_NM = 5e-9
_SPEED_TOL_NM_S = 1e-9


def _canonical_step_pm(step_nm: float) -> float:
    for allowed_pm in ALLOWED_STEP_PM:
        if math.isclose(step_nm, allowed_pm / 1000, rel_tol=0.0, abs_tol=_STEP_TOL_NM):
            return allowed_pm
    allowed = ", ".join(f"{step:g}" for step in ALLOWED_STEP_PM)
    raise ValueError(
        f"Unsupported sweep step: {step_nm:g} nm ({step_nm * 1000:g} pm). "
        f"Allowed steps are {allowed} pm."
    )


def get_allowed_speeds_nm_s(step_nm: float) -> tuple[int, ...]:
    """Return the allowed sweep speeds for a step size in nm."""
    step_pm = _canonical_step_pm(step_nm)
    if step_pm in (0.05, 0.1):
        return (1,)
    return FULL_SPEED_TABLE_NM_S


def validate_sts_sweep_params(
    start_wl: float,
    stop_wl: float,
    step: float,
    speed: float,
) -> None:
    """Validate sweep parameters against the Santec STS software choices.

    Args:
        start_wl: Start wavelength in nm.
        stop_wl: Stop wavelength in nm.
        step: Sweep step in nm.
        speed: Sweep speed in nm/s.
    """
    if not all(math.isfinite(value) for value in (start_wl, stop_wl, step, speed)):
        raise ValueError("Sweep parameters must be finite")
    if start_wl <= 0 or stop_wl <= 0 or start_wl == stop_wl:
        raise ValueError("Wavelength endpoints must be positive and different")
    if abs(stop_wl - start_wl) + _STEP_TOL_NM < step:
        raise ValueError("Sweep span must be at least one step")
    step_pm = _canonical_step_pm(step)
    allowed_speeds = get_allowed_speeds_nm_s(step)
    if not any(math.isclose(speed, allowed, rel_tol=0.0, abs_tol=_SPEED_TOL_NM_S) for allowed in allowed_speeds):
        if step_pm in (0.05, 0.1):
            raise ValueError(f"For {step_pm:g} pm step, speed must be 1 nm/s.")
        allowed = ", ".join(str(speed) for speed in allowed_speeds)
        raise ValueError(
            f"Unsupported sweep speed: {speed:g} nm/s for {step_pm:g} pm step. "
            f"Allowed speeds are {allowed} nm/s."
        )

    span = abs(stop_wl - start_wl)
    if step_pm == 0.05 and span > 1.0 + _STEP_TOL_NM:
        raise ValueError("For 0.05 pm step, sweep range <= 1 nm is required.")
    if step_pm == 0.1 and span > 10.0 + _STEP_TOL_NM:
        raise ValueError("For 0.1 pm step, sweep range <= 10 nm is required.")
