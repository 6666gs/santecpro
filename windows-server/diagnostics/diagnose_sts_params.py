#!/usr/bin/env python
"""Configure STS sweep/logging parameters through official Santec DLLs."""

from __future__ import annotations

import argparse

from santec_dll_backend.instruments import DllMpm, DllTsl
from santecpro.sweep_rules import validate_sts_sweep_params


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tsl", default="GPIB3::1::INSTR")
    parser.add_argument("--mpm", default="GPIB0::16::INSTR")
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--stop", type=float, required=True)
    parser.add_argument("--step", type=float, required=True)
    parser.add_argument("--speed", type=float, required=True)
    args = parser.parse_args()
    validate_sts_sweep_params(args.start, args.stop, args.step, args.speed)

    tsl = DllTsl(args.tsl)
    mpm = DllMpm(args.mpm)
    try:
        tsl.connect()
        mpm.connect()
        actual_step = tsl.set_sts_sweep_parameters(
            args.start, args.stop, args.speed, args.step
        )
        print("requested_step_nm:", args.step)
        print("actual_step_nm:", actual_step)
        mpm.set_sts_logging_parameters(
            args.start, args.stop, args.step, actual_step, args.speed
        )
        print("sts parameter configure: ok")
    finally:
        try:
            mpm.disconnect()
        finally:
            tsl.disconnect()


if __name__ == "__main__":
    main()
