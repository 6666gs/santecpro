#!/usr/bin/env python3
"""Keep the small shared modules identical across the two deployable folders.

``exceptions.py`` and ``sweep_rules.py`` are intentionally duplicated into both
``remote-client/santecpro/`` and ``windows-server/santecpro/`` so each folder is
independently deployable (copy one folder → done). This script keeps the two
copies in sync.

Source of truth: ``remote-client/santecpro/``

Usage::

    python sync_shared.py            # copy source -> windows-server
    python sync_shared.py --check    # exit 1 if copies differ (CI / pre-commit)
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "remote-client" / "santecpro"
DST = ROOT / "windows-server" / "santecpro"
SHARED_MODULES = ("exceptions.py", "sweep_rules.py")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync shared modules between folders.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the copies are identical without writing (exit 1 on drift)",
    )
    args = parser.parse_args()

    drift: list[str] = []
    for name in SHARED_MODULES:
        src, dst = SRC / name, DST / name
        if args.check:
            if not dst.exists() or not filecmp.cmp(src, dst, shallow=False):
                drift.append(name)
        else:
            shutil.copy2(src, dst)
            print(f"synced {name}")

    if args.check:
        if drift:
            print("shared modules differ: " + ", ".join(drift), file=sys.stderr)
            return 1
        print("shared modules are in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
