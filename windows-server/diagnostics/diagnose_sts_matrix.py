#!/usr/bin/env python
"""Probe official DLL STS parameter readback without starting a sweep."""

from __future__ import annotations

import argparse

from santec_dll_backend.instruments import DllMpm, DllTsl
from santecpro.sweep_rules import ALLOWED_STEP_NM, get_allowed_speeds_nm_s


def expected_points(start: float, stop: float, step: float) -> int:
    return int(round(abs(stop - start) / step)) + 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tsl", default="GPIB3::1::INSTR")
    parser.add_argument("--mpm", default="GPIB0::16::INSTR")
    parser.add_argument("--start", type=float, default=1540.0)
    parser.add_argument("--stop", type=float, default=1540.1)
    args = parser.parse_args()

    tsl = DllTsl(args.tsl)
    mpm = DllMpm(args.mpm)
    try:
        tsl.connect()
        mpm.connect()
        print("step_nm,speed_nm_s,requested_points,actual_step_nm,mpm_points")
        for step in ALLOWED_STEP_NM:
            for speed in get_allowed_speeds_nm_s(step):
                requested = expected_points(args.start, args.stop, step)
                actual_step = tsl.set_sts_sweep_parameters(
                    args.start, args.stop, speed, step
                )
                mpm.set_sts_logging_parameters(
                    args.start, args.stop, step, actual_step, speed
                )
                mpm_points = mpm.get_logging_data_point()
                print(f"{step:g},{speed},{requested},{actual_step:g},{mpm_points}")
    finally:
        try:
            mpm.disconnect()
        finally:
            tsl.disconnect()


if __name__ == "__main__":
    main()
