"""Helpers for starting the Windows server over SSH from a client UI."""

from __future__ import annotations

import os
import shlex
import subprocess
from urllib.parse import urlparse


def start_windows_server(
    server_url: str,
    user: str = "shareuser",
    password_env: str = "SANTEC_SSH_PASSWORD",
    windows_dir: str = r"E:\code_pro\windows_server",
    windows_python: str = r"E:\code_pro\python312\python.exe",
    port: int = 5000,
) -> str:
    """Start ``server.py`` on the Windows host through SSH."""
    host = urlparse(server_url).hostname or server_url.replace("http://", "").split(":")[0]
    remote_cmd = (
        f'cmd /c "cd /d {windows_dir} && start \"santec-server\" '
        f'{windows_python} server.py --host 0.0.0.0 --port {port}"'
    )
    command = [
        "ssh",
        "-tt",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/tmp/santec_known_hosts",
        f"{user}@{host}",
        remote_cmd,
    ]
    password = os.environ.get(password_env)
    if password:
        return _run_expect(command, password)
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip())
    return completed.stdout.strip()


def _run_expect(command: list[str], password: str) -> str:
    command_list = " ".join(_tcl_word(part) for part in command)
    script = (
        "set timeout 60\n"
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
    completed = subprocess.run(["expect", "-c", script], env=env, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip())
    return completed.stdout.strip()


def _tcl_word(value: str) -> str:
    if "{" in value or "}" in value:
        raise ValueError(f"Tcl brace characters are not supported: {value!r}")
    return "{" + value + "}"
