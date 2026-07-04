#!/usr/bin/env python
"""Run one minimal STS scan through the official Santec DLLs."""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

from santec_dll_backend.instruments import DllMpm, DllTsl
from santecpro.sweep_rules import validate_sts_sweep_params


def expected_points(start: float, stop: float, step: float) -> int:
    return int(round(abs(stop - start) / step)) + 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tsl", default="GPIB3::1::INSTR")
    parser.add_argument("--mpm", default="GPIB0::16::INSTR")
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--stop", type=float, required=True)
    parser.add_argument("--step", type=float, required=True)
    parser.add_argument("--speed", type=float, required=True)
    parser.add_argument("--module", type=int, default=0)
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--csv", default="")
    args = parser.parse_args()
    validate_sts_sweep_params(args.start, args.stop, args.step, args.speed)

    requested_expected = expected_points(args.start, args.stop, args.step)
    tsl = DllTsl(args.tsl)
    mpm = DllMpm(args.mpm)
    actual_step = None
    powers: list[float] = []
    monitor: list[float] = []

    try:
        tsl.connect()
        print("TSL:", tsl.idn())
        mpm.connect()
        print("MPM:", mpm.idn())

        actual_step = tsl.set_sts_sweep_parameters(
            args.start, args.stop, args.speed, args.step
        )
        print("requested_step_nm:", args.step)
        print("actual_step_nm:", actual_step)
        print("requested_expected_points:", requested_expected)

        mpm.set_sts_logging_parameters(
            args.start, args.stop, args.step, actual_step, args.speed
        )
        print("configured STS logging")
        mpm_expected = mpm.get_logging_data_point()
        print("mpm_expected_points:", mpm_expected)

        tsl.set_continuous_oneway_sweep_mode()
        print("TSL Set_Sweep_Mode Continuous_Oneway")
        tsl.set_waiting_for_trigger_start_mode()
        print("TSL Set_Sweep_Start_Mode WaitingforTrigger")
        mpm.start_logging()
        print("MPM Logging_Start")
        tsl.start_sweep()
        print("TSL Sweep_Start")
        try:
            tsl.wait_for_status(3000, "waiting_for_trigger")
            print("TSL waiting_for_trigger")
            tsl.soft_trigger()
            print("TSL Soft_Trigger")

            wait_ms = int(abs(args.stop - args.start) / args.speed * 1100)
            wait_ms = max(wait_ms, 5000)
            tsl.wait_for_status(wait_ms, "standby")
            print("TSL standby")

            status, count = mpm.wait_for_log_completion()
            print(f"MPM log status={status}, count={count}")
        finally:
            mpm.stop_logging(raise_on_error=False)
            print("MPM Logging_Stop")
            tsl.stop_sweep(raise_on_error=False)
            print("TSL Sweep_Stop")

        powers = mpm.get_channel_log_data(args.module, args.channel)
        print("MPM powers:", len(powers))
        try:
            monitor = tsl.get_sts_power_monitor_data(args.speed, actual_step)
            print("TSL monitor:", len(monitor))
        except Exception as exc:
            monitor = []
            print("TSL monitor read failed:", exc)

        if len(powers) != mpm_expected:
            raise RuntimeError(f"MPM data length mismatch: got {len(powers)}, expected {mpm_expected}")

        if args.csv:
            path = Path(args.csv)
            wavelengths = [
                args.start + i * (args.stop - args.start) / max(1, len(powers) - 1)
                for i in range(len(powers))
            ]
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["wavelength_nm", "power_dbm", "monitor_dbm"])
                for i, power in enumerate(powers):
                    mon = monitor[i] if i < len(monitor) else ""
                    writer.writerow([wavelengths[i], power, mon])
            print("csv:", path)
    finally:
        try:
            mpm.disconnect()
        finally:
            tsl.disconnect()


if __name__ == "__main__":
    main()
