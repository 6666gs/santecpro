#!/usr/bin/env python
"""Try reading MPM trigger/monitor auxiliary data from each slot."""

from __future__ import annotations

import argparse

from santec_dll_backend.instruments import DllMpm, raise_if_error


def try_call(label: str, call) -> None:
    try:
        code, data = call()
        if int(code) != 0:
            print(f"{label}: code={code}")
        else:
            print(f"{label}: code=0, len={len(list(data))}")
    except Exception as exc:
        print(f"{label}: exception={exc}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mpm", default="GPIB0::16::INSTR")
    args = parser.parse_args()

    mpm = DllMpm(args.mpm)
    try:
        mpm.connect()
        print("MPM:", mpm.idn())
        for slot in range(0, 6):
            try_call(
                f"slot {slot} trigger",
                lambda slot=slot: mpm._mpm.Get_216_Triggerdata(slot, None),
            )
            try_call(
                f"slot {slot} monitor",
                lambda slot=slot: mpm._mpm.Get_216_Monitordata(slot, None, None),
            )
            try_call(
                f"slot {slot} module_log",
                lambda slot=slot: mpm._mpm.Get_Each_Module_Loggdata(slot, None),
            )
    finally:
        mpm.disconnect()


if __name__ == "__main__":
    main()
