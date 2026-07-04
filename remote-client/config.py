"""Client configuration — one place to point the client at your Windows server.

Every value can be overridden by an environment variable, so you rarely need to
edit this file in place. Example::

    export SANTEC_SERVER_URL="http://10.0.0.5:5000"
"""

from __future__ import annotations

import os

# --- Server endpoint -------------------------------------------------------
# The Windows PC's IP and the port server.py listens on. This is the ONE value
# most deployments need to change.
SERVER_URL = os.getenv("SANTEC_SERVER_URL", "http://192.168.100.103:5000")

# --- Instrument GPIB addresses (shown in the UI) ---------------------------
TSL_ADDRESS = os.getenv("SANTEC_TSL_ADDRESS", "GPIB3::1::INSTR")
MPM_ADDRESS = os.getenv("SANTEC_MPM_ADDRESS", "GPIB0::16::INSTR")

# --- SSH (only used by server_control.py and remote_sts_scan.py) -----------
SSH_USER = os.getenv("SANTEC_SSH_USER", "shareuser")
SSH_PASSWORD_ENV = os.getenv("SANTEC_SSH_PASSWORD_ENV", "SANTEC_SSH_PASSWORD")
SERVER_PORT = int(os.getenv("SANTEC_SERVER_PORT", "5000"))
WINDOWS_DIR = os.getenv("SANTEC_WINDOWS_DIR", r"E:\code_pro\windows_server")
WINDOWS_PYTHON = os.getenv("SANTEC_WINDOWS_PYTHON", r"E:\code_pro\python312\python.exe")
