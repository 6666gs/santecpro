#!/usr/bin/env python
"""Print selected method names from the official Santec DLL classes."""

from __future__ import annotations

from santec_dll_backend.loader import load_santec_dlls


def dump_methods(title: str, obj: object, keywords: tuple[str, ...]) -> None:
    print(f"[{title}]")
    names = sorted({name for name in dir(obj) if any(k.lower() in name.lower() for k in keywords)})
    for name in names:
        print(name)
    print()


def main() -> None:
    load_santec_dlls()
    from Santec import MPM, TSL
    from Santec.STSProcess import ILSTS

    dump_methods("MPM", MPM(), ("trigger", "log", "sts", "data"))
    dump_methods("TSL", TSL(), ("trigger", "log", "sts", "data", "monitor"))
    dump_methods("ILSTS", ILSTS(), ("ref", "meas", "monitor", "wave", "rescal", "target", "data"))


if __name__ == "__main__":
    main()
