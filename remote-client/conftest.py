"""Pytest bootstrap for the remote client package.

Ensures this folder is importable so ``import santecpro`` and ``import config``
resolve when running the test suite from ``remote-client/``.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
