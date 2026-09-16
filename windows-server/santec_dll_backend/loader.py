"""Load the official Santec .NET DLLs from a local vendor directory."""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


DEFAULT_DLL_DIR = Path(__file__).resolve().parents[1] / "vendor" / "santec_dll"


def load_santec_dlls(dll_dir: str | os.PathLike[str] | None = None) -> Path:
    """Load Santec.Instrument.dll and STSProcess.dll with pythonnet.

    The DLLs are Windows/.NET assemblies. This function intentionally imports
    ``clr`` lazily so this module can still be imported on macOS for tests and
    packaging.
    """
    if platform.system() != "Windows":
        raise RuntimeError("Santec DLL backend can only run on Windows.")

    resolved = Path(dll_dir or os.getenv("SANTEC_DLL_DIR") or DEFAULT_DLL_DIR).resolve()
    instrument = resolved / "Santec.Instrument.dll"
    sts_process = resolved / "STSProcess.dll"
    missing = [str(p) for p in (instrument, sts_process) if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing Santec DLLs: " + ", ".join(missing))

    os.environ["PATH"] = str(resolved) + os.pathsep + os.environ.get("PATH", "")
    if str(resolved) not in sys.path:
        sys.path.insert(0, str(resolved))

    import clr  # type: ignore

    clr.AddReference(str(instrument))
    clr.AddReference(str(sts_process))
    return resolved

