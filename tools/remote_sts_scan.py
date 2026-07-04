#!/usr/bin/env python3
"""Run a Windows-side STSProcess scan from macOS over SSH.

This is a thin remote-control wrapper. The actual instrument/DLL work stays on
the Windows host in ``E:\\code_pro\\windows_server\\diagnose_stsprocess_scan.py``.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


DEFAULT_HOST = "192.168.100.103"
DEFAULT_USER = "shareuser"
DEFAULT_WINDOWS_DIR = r"E:\code_pro\windows_server"
DEFAULT_WINDOWS_PYTHON = r"E:\code_pro\python312\python.exe"
DEFAULT_SCRIPT = "diagnose_stsprocess_scan.py"
DEFAULT_TSL = "GPIB3::1::INSTR"
DEFAULT_MPM = "GPIB0::16::INSTR"
KNOWN_HOSTS = "/tmp/santec_known_hosts"


def _step_nm(args: argparse.Namespace) -> float:
    if args.step_nm is not None and args.step_pm is not None:
        raise SystemExit("Use only one of --step-nm or --step-pm.")
    if args.step_nm is not None:
        return args.step_nm
    if args.step_pm is not None:
        return args.step_pm / 1000.0
    raise SystemExit("One of --step-nm or --step-pm is required.")


def _remote_csv_path(args: argparse.Namespace) -> str:
    if args.csv:
        name = args.csv
    else:
        step_pm = _step_nm(args) * 1000.0
        name = f"sts_{args.start:g}_{args.stop:g}_{step_pm:g}pm_{args.speed:g}nms.csv"
    # Keep the remote CSV in the Windows working directory unless a full path is
    # explicitly supplied by the caller.
    if ":" in name or "\\" in name or "/" in name:
        return name
    return rf"{args.windows_dir}\{name}"


def _build_remote_command(args: argparse.Namespace, csv_path: str) -> str:
    step_nm = _step_nm(args)
    parts = [
        args.windows_python,
        args.script,
        "--tsl",
        args.tsl,
        "--mpm",
        args.mpm,
        "--start",
        f"{args.start:g}",
        "--stop",
        f"{args.stop:g}",
        "--step",
        f"{step_nm:g}",
        "--speed",
        f"{args.speed:g}",
        "--module",
        str(args.module),
        "--channel",
        str(args.channel),
        "--range",
        str(args.mpm_range),
    ]
    if args.avg_ms is not None:
        parts.extend(["--avg-ms", f"{args.avg_ms:g}"])
    if csv_path:
        parts.extend(["--csv", csv_path])

    # Windows cmd quoting is simpler if the whole command is wrapped once.
    remote_scan = subprocess.list2cmdline(parts)
    return f'cmd /c "cd /d {args.windows_dir} && {remote_scan}"'


def _ssh_base(args: argparse.Namespace) -> list[str]:
    return [
        "ssh",
        "-tt",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        f"UserKnownHostsFile={KNOWN_HOSTS}",
        f"{args.user}@{args.host}",
    ]


def _scp_base(args: argparse.Namespace) -> list[str]:
    return [
        "scp",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        f"UserKnownHostsFile={KNOWN_HOSTS}",
    ]


def _run_with_optional_expect(command: list[str], password: str | None) -> int:
    if not password:
        return subprocess.run(command).returncode

    command_list = " ".join(_tcl_word(part) for part in command)
    expect_script = (
        "set timeout -1\n"
        f"set cmd [list {command_list}]\n"
        "spawn {*}$cmd\n"
        "expect {\n"
        '  "*assword:*" { send -- "$env(SANTEC_REMOTE_PASSWORD)\\r"; exp_continue }\n'
        "  eof\n"
        "}\n"
        "catch wait result\n"
        "exit [lindex $result 3]\n"
    )
    env = os.environ.copy()
    env["SANTEC_REMOTE_PASSWORD"] = password
    return subprocess.run(["expect", "-c", expect_script], env=env).returncode


def _tcl_word(value: str) -> str:
    if "{" in value or "}" in value:
        raise ValueError(f"Tcl brace characters are not supported in command argument: {value!r}")
    return "{" + value + "}"


def _scp_remote_path(windows_path: str) -> str:
    return windows_path.replace("\\", "/")


def _pull_csv(args: argparse.Namespace, remote_csv: str, password: str | None) -> int:
    local_dir = Path(args.local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    local_name = args.local_name or Path(remote_csv.replace("\\", "/")).name
    local_path = local_dir / local_name
    remote_spec = f"{args.user}@{args.host}:{_scp_remote_path(remote_csv)}"
    command = [*_scp_base(args), remote_spec, str(local_path)]
    print(f"Pulling CSV to {local_path}")
    return _run_with_optional_expect(command, password)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Windows-side Santec STSProcess scan from macOS."
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password-env", default="SANTEC_SSH_PASSWORD")
    parser.add_argument("--windows-dir", default=DEFAULT_WINDOWS_DIR)
    parser.add_argument("--windows-python", default=DEFAULT_WINDOWS_PYTHON)
    parser.add_argument("--script", default=DEFAULT_SCRIPT)
    parser.add_argument("--tsl", default=DEFAULT_TSL)
    parser.add_argument("--mpm", default=DEFAULT_MPM)
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--stop", type=float, required=True)
    parser.add_argument("--step-pm", type=float)
    parser.add_argument("--step-nm", type=float)
    parser.add_argument("--speed", type=float, required=True)
    parser.add_argument("--module", type=int, default=0)
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--range", type=int, default=1, dest="mpm_range")
    parser.add_argument("--avg-ms", type=float, default=0.01)
    parser.add_argument("--csv", default="")
    parser.add_argument("--pull", action="store_true")
    parser.add_argument("--local-dir", default="scan_results")
    parser.add_argument("--local-name", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    remote_csv = _remote_csv_path(args)
    remote_command = _build_remote_command(args, remote_csv)
    ssh_command = [*_ssh_base(args), remote_command]
    password = os.environ.get(args.password_env)

    print("Remote command:")
    print(remote_command)
    if args.pull:
        print(f"Remote CSV: {remote_csv}")
    if args.dry_run:
        return 0

    code = _run_with_optional_expect(ssh_command, password)
    if code != 0:
        return code
    if args.pull:
        return _pull_csv(args, remote_csv, password)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
