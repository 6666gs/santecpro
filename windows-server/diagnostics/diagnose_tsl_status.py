#!/usr/bin/env python
"""Probe TSL sweep status values through the Santec DLL."""

from __future__ import annotations

import time

from santec_dll_backend.instruments import DllTsl


def read_enum(method, enum_value):
    result = method(enum_value)
    if isinstance(result, tuple):
        return int(result[0]), result[1]
    return int(result), enum_value


def main() -> None:
    tsl = DllTsl("GPIB3::1::INSTR")
    try:
        tsl.connect()
        print("idn:", tsl.idn())

        code, mode = read_enum(
            tsl._tsl.Get_Sweep_Start_Mode, tsl._tsl.Sweep_Start_Mode.Normal
        )
        print("start_mode before:", code, mode)
        code, sweep_mode = read_enum(tsl._tsl.Get_Sweep_Mode, tsl._tsl.Sweep_Mode.Step_Oneway)
        print("sweep_mode before:", code, sweep_mode)
        code, ld = read_enum(tsl._tsl.Get_LD_Status, tsl._tsl.LD_Status.LD_OFF)
        print("ld_status:", code, ld)
        code, shutter = read_enum(
            tsl._tsl.Get_Shutter_Status, tsl._tsl.Shutter_Status.Shutter_Close
        )
        print("shutter_status:", code, shutter)
        code, trig_out = read_enum(
            tsl._tsl.Get_Trigger_Output_Mode, getattr(tsl._tsl.Trigger_Output_Mode, "None")
        )
        print("trigger_output_mode:", code, trig_out)
        code, trig_source = read_enum(
            tsl._tsl.Get_TriggerOutput_Source, tsl._tsl.TriggerOut_Source.Sweep
        )
        print("trigger_output_source:", code, trig_source)
        code, trig_in = read_enum(
            tsl._tsl.Get_Input_Trigger_Mode, tsl._tsl.Trigger_Input_Mode.Disable
        )
        print("trigger_input_mode:", code, trig_in)

        actual_step = tsl.set_sts_sweep_parameters(1540, 1540.01, 1, 0.001)
        print("actual_step:", actual_step)
        tsl.set_continuous_oneway_sweep_mode()
        tsl.set_waiting_for_trigger_start_mode()

        code, mode = read_enum(
            tsl._tsl.Get_Sweep_Start_Mode, tsl._tsl.Sweep_Start_Mode.Normal
        )
        print("start_mode after:", code, mode)
        code, sweep_mode = read_enum(tsl._tsl.Get_Sweep_Mode, tsl._tsl.Sweep_Mode.Step_Oneway)
        print("sweep_mode after:", code, sweep_mode)

        code, status = read_enum(tsl._tsl.Get_Sweep_Status, tsl._tsl.Sweep_Status.Standby)
        print("status before start:", code, status)

        tsl.start_sweep()
        print("start_sweep")
        for i in range(20):
            code, status = read_enum(
                tsl._tsl.Get_Sweep_Status, tsl._tsl.Sweep_Status.Standby
            )
            print("status", i, code, status)
            time.sleep(0.2)
    finally:
        try:
            tsl.stop_sweep(False)
        finally:
            tsl.disconnect()


if __name__ == "__main__":
    main()
