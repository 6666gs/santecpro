#!/usr/bin/env python
"""Close shutter, turn on TSL LD, and poll LD status."""

from __future__ import annotations

import argparse
import time

from santec_dll_backend.instruments import DllTsl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tsl", default="GPIB3::1::INSTR")
    parser.add_argument("--timeout", type=float, default=360.0)
    parser.add_argument("--interval", type=float, default=10.0)
    args = parser.parse_args()

    tsl = DllTsl(args.tsl)
    try:
        tsl.connect()
        print("TSL:", tsl.idn())
        print("Set shutter close:", tsl._tsl.Set_Shutter_Status(tsl._tsl.Shutter_Status.Shutter_Close))
        print("Set LD on:", tsl._tsl.Set_LD_Status(tsl._tsl.LD_Status.LD_ON))

        deadline = time.monotonic() + args.timeout
        i = 0
        while True:
            status = tsl._tsl.Get_LD_Status(tsl._tsl.LD_Status.LD_OFF)
            print("LD status:", i, status)
            if isinstance(status, tuple) and str(status[1]).endswith("LD_ON"):
                print("LD ready")
                return
            if time.monotonic() >= deadline:
                raise TimeoutError(f"LD did not become ON within {args.timeout}s")
            i += 1
            time.sleep(args.interval)
    finally:
        tsl.disconnect()


if __name__ == "__main__":
    main()
