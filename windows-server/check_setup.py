#!/usr/bin/env python3
"""Preflight environment check for the Windows Santec server.

Run this on the Windows measurement PC before ``python server.py``. It verifies
Python, dependencies, vendor DLLs, .NET/pythonnet DLL loading, and VISA/GPIB,
then prints a clear go / no-go so problems surface here instead of mid-scan.

Usage::

    python check_setup.py             # check only
    python check_setup.py --install   # pip install -r requirements.txt, then check
"""

from __future__ import annotations

import argparse
import importlib
import platform
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import config

IS_WINDOWS = platform.system() == "Windows"

OK, WARN, FAIL, SKIP = "[ OK ]", "[WARN]", "[FAIL]", "[SKIP]"

REQUIRED_DLLS = ("Santec.Instrument.dll", "STSProcess.dll")
SUPPORT_DLLS = (
    "NationalInstruments.NI4882.dll",
    "NationalInstruments.Common.dll",
    "NationalInstruments.VisaNS.dll",
    "NationalInstruments.DAQmx.dll",
    "Ivi.Visa.dll",
    "Keysight.Visa.dll",
    "FTD2XX_NET.dll",
)
# pip distribution name -> import module name
DEPS = {"flask": "flask", "numpy": "numpy", "pyvisa": "pyvisa", "pythonnet": "clr"}

_fail = 0
_warn = 0


def line(level: str, msg: str) -> None:
    global _fail, _warn
    if level == FAIL:
        _fail += 1
    elif level == WARN:
        _warn += 1
    print(f"  {level} {msg}")


def header(title: str) -> None:
    print(f"\n{title}")


def win_level() -> str:
    """FAIL on Windows (where the check must pass), WARN elsewhere."""
    return FAIL if IS_WINDOWS else WARN


def do_install() -> None:
    header("Installing dependencies (pip install -r requirements.txt)")
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(HERE / "requirements.txt")]
    )
    line(OK if proc.returncode == 0 else FAIL,
         "dependencies installed" if proc.returncode == 0 else "pip install failed (see output above)")


def check_python() -> None:
    header("Python")
    v = sys.version_info
    msg = f"Python {v.major}.{v.minor}.{v.micro} on {platform.system()} ({platform.machine()})"
    line(OK if (v.major, v.minor) >= (3, 10) else FAIL,
         msg if (v.major, v.minor) >= (3, 10) else msg + "  -- need 3.10+")
    if not IS_WINDOWS:
        line(WARN, "not running on Windows -- DLL/VISA checks below are informational only")


def check_deps() -> None:
    header("Python dependencies")
    for dist, mod in DEPS.items():
        try:
            importlib.import_module(mod)
            line(OK, f"{dist} importable")
        except Exception as exc:
            if dist == "pythonnet":
                line(win_level(), f"pythonnet/clr not importable: {exc}")
            else:
                line(FAIL, f"{dist} not importable -- run: pip install {dist}  ({exc})")


def check_dlls() -> None:
    header(f"Vendor DLLs  ({config.DLL_DIR})")
    dll_dir = Path(config.DLL_DIR)
    if not dll_dir.is_dir():
        line(FAIL, f"DLL directory missing: {dll_dir} (see vendor/README.md for how to obtain the DLLs)")
        return
    for name in REQUIRED_DLLS:
        line(OK, name) if (dll_dir / name).exists() else line(FAIL, f"{name} MISSING (required; see vendor/README.md)")
    for name in SUPPORT_DLLS:
        line(OK, name) if (dll_dir / name).exists() else line(WARN, f"{name} missing (may be needed for GPIB)")


def check_dll_loading() -> None:
    header("DLL loading (pythonnet / .NET)")
    if not IS_WINDOWS:
        line(SKIP, "DLL loading is Windows-only")
        return
    try:
        from santec_dll_backend.loader import load_santec_dlls

        load_santec_dlls(config.DLL_DIR)
        line(OK, "Santec.Instrument.dll + STSProcess.dll loaded via pythonnet")
    except Exception as exc:
        line(FAIL, f"could not load DLLs: {exc}")


def check_visa() -> None:
    header("VISA / GPIB")
    try:
        import pyvisa
    except Exception as exc:
        line(win_level(), f"pyvisa not importable: {exc}")
        return
    try:
        rm = pyvisa.ResourceManager()
    except Exception as exc:
        line(win_level(), f"no VISA backend found (install NI-VISA runtime): {exc}")
        return
    try:
        resources = list(rm.list_resources())
    except Exception as exc:
        line(WARN, f"could not list VISA resources: {exc}")
        return
    if resources:
        line(OK, f"{len(resources)} VISA resource(s): {', '.join(resources)}")
    else:
        line(WARN, "no VISA instruments detected (are TSL/MPM powered on and on the GPIB bus?)")
    for label, addr in (("TSL", config.TSL_ADDRESS), ("MPM", config.MPM_ADDRESS)):
        line(OK, f"{label} detected at {addr}") if addr in resources \
            else line(WARN, f"{label} configured as {addr} but not among detected resources")


def print_config() -> None:
    header("Configured values (edit windows-server/config.py or set env vars)")
    print(f"  HOST={config.HOST}  PORT={config.PORT}")
    print(f"  TSL_ADDRESS={config.TSL_ADDRESS}  MPM_ADDRESS={config.MPM_ADDRESS}")
    print(f"  DLL_DIR={config.DLL_DIR}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight check for the Windows Santec server.")
    parser.add_argument(
        "--install", action="store_true",
        help="pip install -r requirements.txt before checking",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Santec windows-server -- setup check")
    print("=" * 60)

    print_config()
    if args.install:
        do_install()
    check_python()
    check_deps()
    check_dlls()
    check_dll_loading()
    check_visa()

    header("Summary")
    if _fail:
        print(f"  NOT READY -- {_fail} failure(s), {_warn} warning(s). Fix the [FAIL] items above.")
        return 1
    if _warn:
        print(f"  READY (with {_warn} warning[s]) -- review [WARN] items, then run:  python server.py")
        return 0
    print("  READY -- run:  python server.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
