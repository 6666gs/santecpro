"""Standalone stdlib-only inventory. No clr, DLL loading, scans or file changes.

Copy anywhere on Windows and run: python diagnose_ni_install.py
"""
import os
from pathlib import Path
import platform
import struct
import sys


def machine(path):
    try:
        with path.open('rb') as f:
            header = f.read(64)
            if len(header) != 64 or header[:2] != b'MZ':
                return 'invalid PE'
            f.seek(struct.unpack_from('<I', header, 60)[0])
            pe = f.read(6)
            if len(pe) != 6 or pe[:4] != b'PE\0\0':
                return 'invalid PE'
            value = struct.unpack_from('<H', pe, 4)[0]
            return {0x8664: 'x64', 0x14c: 'x86'}.get(value, hex(value))
    except OSError as exc:
        return str(exc)


def main():
    print(f'Python: {sys.executable} ({struct.calcsize("P") * 8}-bit)')
    print(f'OS: {platform.platform()}')
    if os.name != 'nt':
        print('Run this inventory on the Windows measurement PC.')
        return
    windows = Path(os.getenv('WINDIR', r'C:\Windows'))
    print(f'Native NI driver present: {(windows / "System32" / "nicaiu.dll").exists()}')
    roots = [windows/'Microsoft.NET'/'assembly', windows/'assembly']
    for env, default in [('ProgramFiles', r'C:\Program Files'),
                         ('ProgramFiles(x86)', r'C:\Program Files (x86)')]:
        base = Path(os.getenv(env, default))
        roots.extend([base/'National Instruments', base/'IVI Foundation'])
    found = set()
    for root in roots:
        print(f'Searching: {root}', flush=True)
        if not root.exists():
            continue
        for parent, _, files in os.walk(root, onerror=lambda e: print(f'Cannot read: {e}')):
            for name in files:
                if name.lower() == 'nationalinstruments.daqmx.dll':
                    found.add(Path(parent)/name)
    print('\nNI DAQmx .NET files:')
    if not found:
        print('NONE found in the searched installation locations.')
    for path in sorted(found):
        print(f'  {machine(path)} | {path}')
    print('\nInventory only: no DLL loaded, no hardware commands, no files changed.')


if __name__ == '__main__':
    main()
