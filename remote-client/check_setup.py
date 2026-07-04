#!/usr/bin/env python3
"""Preflight environment check for the Santec remote client.

Verifies Python, dependencies, and connectivity to the Windows server, then
prints a clear go / no-go so problems surface before you open the UI.

Usage::

    python check_setup.py                       # check (uses config.SERVER_URL)
    python check_setup.py --install             # pip install -r requirements.txt first
    python check_setup.py --url http://IP:5000  # test a specific server URL
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

OK, WARN, FAIL = "[ OK ]", "[WARN]", "[FAIL]"

# pip distribution -> (import name, critical?, note-when-missing)
DEPS = {
    "requests": ("requests", True, "required for all remote control"),
    "numpy": ("numpy", True, "required for results/IL math"),
    "matplotlib": ("matplotlib", False, "only needed for plotting"),
    "PyQt5": ("PyQt5", False, "only needed for the GUI (run_ui.py)"),
}

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


def check_deps() -> None:
    header("Python dependencies")
    for dist, (mod, critical, note) in DEPS.items():
        try:
            importlib.import_module(mod)
            line(OK, f"{dist} importable")
        except Exception as exc:
            line(FAIL if critical else WARN, f"{dist} not importable ({note}) -- pip install {dist}  [{exc}]")


def check_server(url: str) -> None:
    status_url = url.rstrip("/") + "/api/status"
    header(f"Server connectivity  ({status_url})")
    try:
        import requests
    except Exception:
        line(WARN, "requests not installed -- cannot test connectivity")
        return
    try:
        resp = requests.get(status_url, timeout=5)
    except requests.exceptions.ConnectionError:
        line(WARN, "connection refused / host unreachable")
        line(WARN, "is server.py running on the Windows PC, and is SERVER_URL's IP/port correct?")
        return
    except requests.exceptions.Timeout:
        line(WARN, "connection timed out (5s) -- check the IP/port and Windows firewall for port 5000")
        return
    except Exception as exc:
        line(WARN, f"cannot reach server: {exc}")
        return
    if resp.status_code != 200:
        line(WARN, f"server responded HTTP {resp.status_code} (expected 200)")
        return
    line(OK, "server reachable (HTTP 200 from /api/status)")
    try:
        data = resp.json()
    except Exception:
        line(WARN, "response was not JSON")
        return
    tsl, mpm = data.get("tsl_idn"), data.get("mpm_idn")
    if tsl or mpm:
        line(OK, f"TSL: {tsl or '(not connected)'}")
        line(OK, f"MPM: {mpm or '(not connected)'}")
    else:
        line(WARN, "server up but instruments not connected yet (connect via the UI or /api/connect)")


def print_config(url: str) -> None:
    header("Configured values (edit remote-client/config.py or set env vars)")
    print(f"  SERVER_URL={config.SERVER_URL}" + ("" if url == config.SERVER_URL else f"   (overridden -> {url})"))
    print(f"  TSL_ADDRESS={config.TSL_ADDRESS}  MPM_ADDRESS={config.MPM_ADDRESS}")
    print(f"  SSH_USER={config.SSH_USER}  WINDOWS_DIR={config.WINDOWS_DIR}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight check for the Santec remote client.")
    parser.add_argument("--install", action="store_true",
                        help="pip install -r requirements.txt before checking")
    parser.add_argument("--url", default=config.SERVER_URL,
                        help="server URL to test (default: config.SERVER_URL)")
    args = parser.parse_args()

    print("=" * 60)
    print("  Santec remote-client -- setup check")
    print("=" * 60)

    print_config(args.url)
    if args.install:
        do_install()
    check_python()
    check_deps()
    check_server(args.url)

    header("Summary")
    if _fail:
        print(f"  NOT READY -- {_fail} failure(s), {_warn} warning(s). Fix the [FAIL] items above.")
        return 1
    if _warn:
        print(f"  READY (with {_warn} warning[s]) -- review [WARN] items, then run:  python run_ui.py")
        return 0
    print("  READY -- run:  python run_ui.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
