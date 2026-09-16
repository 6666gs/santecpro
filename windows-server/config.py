"""Server configuration — defaults for server.py on the Windows host.

Every value can be overridden by an environment variable or a command-line flag
(flags win over env vars, which win over these defaults). Example::

    set SANTEC_TSL_ADDRESS=GPIB1::5::INSTR
"""

from __future__ import annotations

import os
from pathlib import Path

HOST = os.getenv("SANTEC_HOST", "0.0.0.0")
PORT = int(os.getenv("SANTEC_PORT", "5000"))

TSL_ADDRESS = os.getenv("SANTEC_TSL_ADDRESS", "GPIB3::1::INSTR")
MPM_ADDRESS = os.getenv("SANTEC_MPM_ADDRESS", "GPIB0::16::INSTR")

# Directory holding the Santec/NI/Keysight DLLs (see vendor/README.md).
DLL_DIR = os.getenv(
    "SANTEC_DLL_DIR",
    str(Path(__file__).resolve().parent / "vendor" / "santec_dll"),
)

# Confirmed laboratory DAQ; set empty only for supported MPM internal-trigger hardware.
DAQ_DEVICE = os.getenv("SANTEC_DAQ_DEVICE", "Dev1")
