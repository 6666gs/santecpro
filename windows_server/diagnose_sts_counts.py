#!/usr/bin/env python
"""Print DLL logging-point behavior for several STS parameter sets."""

from __future__ import annotations

from santec_dll_backend.instruments import DllMpm, DllTsl


CASES = [
    (1540.0, 1540.01, 0.001, 1.0),
    (1540.0, 1540.01, 0.01, 1.0),
    (1540.0, 1540.1, 0.001, 1.0),
    (1540.0, 1540.1, 0.01, 1.0),
]


def main() -> None:
    tsl = DllTsl("GPIB3::1::INSTR")
    mpm = DllMpm("GPIB0::16::INSTR")
    try:
        tsl.connect()
        mpm.connect()
        print("MPM logging methods:", [n for n in dir(mpm._mpm) if "Logging" in n or "Log" in n])
        for start, stop, step, speed in CASES:
            actual = tsl.set_sts_sweep_parameters(start, stop, speed, step)
            mpm.set_sts_logging_parameters(start, stop, step, actual, speed)
            expected = int(round(abs(stop - start) / step)) + 1
            print("case:", start, stop, step, speed, "actual_step:", actual, "expected:", expected)
            if hasattr(mpm._mpm, "Get_Logging_Data_Point"):
                try:
                    print("  Get_Logging_Data_Point:", mpm._mpm.Get_Logging_Data_Point(0))
                except Exception as exc:
                    print("  Get_Logging_Data_Point error:", type(exc).__name__, exc)
    finally:
        try:
            mpm.disconnect()
        finally:
            tsl.disconnect()


if __name__ == "__main__":
    main()
