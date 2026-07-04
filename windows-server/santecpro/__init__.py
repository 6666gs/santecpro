"""santecpro (server subset) — SCPI fallback drivers for the Windows server.

This trimmed copy provides the direct-VISA instrument drivers and the Scanner
coordinator used by the optional SCPI fallback path in ``server.py``. The
primary scan path is the DLL backend in ``santec_dll_backend``. Kept as a
lightweight package init so importing it does not pull pyvisa/Qt eagerly.
"""

__version__ = "1.0.0"

__all__ = ["__version__"]
