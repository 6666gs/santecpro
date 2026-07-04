#!/usr/bin/env python
"""Run one DLL scan and pass raw data through STSProcess rescaling."""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

from santec_dll_backend.instruments import DllMpm, DllStsProcess, DllTsl
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
    parser.add_argument("--range", type=int, default=1, dest="mpm_range")
    parser.add_argument("--avg-ms", type=float, default=0.01)
    parser.add_argument("--csv", default="")
    args = parser.parse_args()
    validate_sts_sweep_params(args.start, args.stop, args.step, args.speed)

    tsl = DllTsl(args.tsl)
    mpm = DllMpm(args.mpm)
    sts = DllStsProcess()
    actual_step = 0.0
    powers: list[float] = []
    trigger: list[float] = []
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
        print("target_expected_points:", expected_points(args.start, args.stop, args.step))

        sts.make_wavelength_tables(args.start, args.stop, args.step, actual_step)
        target_wavelength = sts.get_target_wavelength_table()
        print("sts_target_wavelength_points:", len(target_wavelength))

        mpm.set_sts_logging_parameters(
            args.start, args.stop, args.step, actual_step, args.speed
        )
        raw_expected = mpm.get_logging_data_point()
        print("mpm_expected_raw_points:", raw_expected)

        tsl.set_continuous_oneway_sweep_mode()
        tsl.set_waiting_for_trigger_start_mode()
        mpm.start_logging()
        print("MPM Logging_Start")
        tsl.start_sweep()
        print("TSL Sweep_Start")
        try:
            tsl.wait_for_status(3000, "waiting_for_trigger")
            tsl.soft_trigger()
            print("TSL Soft_Trigger")
            wait_ms = int(abs(args.stop - args.start) / args.speed * 1100)
            wait_ms = max(wait_ms, 5000)
            tsl.wait_for_status(wait_ms, "standby")
            status, count = mpm.wait_for_log_completion()
            print(f"MPM log status={status}, count={count}")
        finally:
            mpm.stop_logging(raise_on_error=False)
            tsl.stop_sweep(raise_on_error=False)

        powers = mpm.get_channel_log_data(args.module, args.channel)
        print("raw_mpm_power_points:", len(powers))
        aux_available = True
        try:
            trigger = mpm.get_trigger_data(args.module)
            print("raw_trigger_points:", len(trigger))
            monitor = tsl.get_sts_power_monitor_data(args.speed, actual_step)
            print("raw_monitor_points:", len(monitor))
        except Exception as exc:
            print("separate trigger/TSL monitor read failed:", exc)
            try:
                trigger, monitor = mpm.get_216_monitor_data(args.module)
                print("raw_216_trigger_points:", len(trigger))
                print("raw_216_monitor_points:", len(monitor))
            except Exception as aux_exc:
                print("MPM 216 monitor read failed:", aux_exc)
                aux_available = False

        data_struct = sts.make_data_struct(args.module, args.channel, args.mpm_range)
        if aux_available:
            sts.set_tsl_monitor_rescaling(args.avg_ms)
            sts.add_reference_data(powers, trigger, monitor, data_struct)
        else:
            trigger = [float(i) for i in range(len(powers))]
            monitor = [0.0] * len(powers)
            sts.set_tsl_monitor_rescaling(args.avg_ms)
            sts.add_reference_data(powers, trigger, monitor, data_struct)
        wavelength, rescaled_power, rescaled_monitor = sts.rescale_reference(data_struct)
        print("rescaled_wavelength_points:", len(wavelength))
        print("rescaled_power_points:", len(rescaled_power))
        print("rescaled_monitor_points:", len(rescaled_monitor))
        if wavelength:
            print("rescaled_start_stop:", wavelength[0], wavelength[-1])

        if args.csv:
            path = Path(args.csv)
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["wavelength_nm", "power_dbm", "monitor_dbm"])
                for i, wavelength_nm in enumerate(wavelength):
                    power = rescaled_power[i] if i < len(rescaled_power) else ""
                    mon = rescaled_monitor[i] if i < len(rescaled_monitor) else ""
                    writer.writerow([wavelength_nm, power, mon])
            print("csv:", path)
    finally:
        try:
            mpm.disconnect()
        finally:
            tsl.disconnect()


if __name__ == "__main__":
    main()
