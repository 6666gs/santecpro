#!/usr/bin/env python
"""Connect to TSL and MPM through the official Santec DLLs."""

from __future__ import annotations

import argparse

from santec_dll_backend.instruments import DllMpm, DllTsl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tsl", default="GPIB3::1::INSTR")
    parser.add_argument("--mpm", default="GPIB0::16::INSTR")
    args = parser.parse_args()

    tsl = DllTsl(args.tsl)
    mpm = DllMpm(args.mpm)
    try:
        tsl.connect()
        print("TSL:", tsl.idn())
        mpm.connect()
        print("MPM:", mpm.idn())
    finally:
        try:
            mpm.disconnect()
        finally:
            tsl.disconnect()


if __name__ == "__main__":
    main()

