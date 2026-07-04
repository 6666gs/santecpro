#!/usr/bin/env python
"""Check that Windows Python can load the official Santec DLLs."""

from __future__ import annotations

import platform
import sys

from santec_dll_backend.loader import load_santec_dlls


def main() -> None:
    print("python:", sys.version)
    print("architecture:", platform.architecture()[0])
    dll_dir = load_santec_dlls()
    print("dll_dir:", dll_dir)

    from Santec import TSL, MPM
    from Santec.STSProcess import ILSTS

    print("Santec.TSL:", TSL)
    print("Santec.MPM:", MPM)
    print("Santec.STSProcess.ILSTS:", ILSTS)
    print("dll load: ok")


if __name__ == "__main__":
    main()

