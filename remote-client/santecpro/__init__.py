"""santecpro (client) — remote-control driver for the Santec scanning server.

This is the *control-machine* package. It drives a Windows-hosted Flask server
over HTTP and does all post-processing (IL, CSV, plotting) locally. It has no
hardware or DLL dependency and runs anywhere, macOS included.
"""

__version__ = "1.0.0"

from santecpro.results import ScanResult, ILMeasurement, merge_multi_range, calculate_il
from santecpro.remote import RemoteScanner

__all__ = [
    "RemoteScanner",
    "ScanResult",
    "ILMeasurement",
    "merge_multi_range",
    "calculate_il",
]
