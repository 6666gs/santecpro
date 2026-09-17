"""Load the official Santec .NET DLLs from a local vendor directory."""

from __future__ import annotations

import os
import ntpath
import threading
import platform
import sys
from pathlib import Path


_load_lock = threading.RLock()


def _path_key(value: str) -> str:
    """Compare Windows search paths including case, separators and quotes."""
    return ntpath.normcase(ntpath.normpath(value.strip('"')))


def _configure_search_path(directory: Path) -> None:
    """Keep one vendor entry without touching unrelated PATH entries."""
    value = str(directory)
    key = _path_key(value)
    current = os.environ.get("PATH", "")
    entries = current.split(os.pathsep) if current else []
    updated = os.pathsep.join([value, *[p for p in entries if _path_key(p) != key]])
    if updated != current:
        os.environ["PATH"] = updated
    if not any(isinstance(p, str) and _path_key(p) == key for p in sys.path):
        sys.path.insert(0, value)


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

    # Instrument wrappers call this repeatedly, including during monitoring.
    # Serialize initialization and never append another copy to the process PATH.
    with _load_lock:
        quarantine_x86_daq(resolved)
        _configure_search_path(resolved)

        import clr  # type: ignore

        clr.AddReference(str(instrument))
        clr.AddReference(str(sts_process))
    return resolved


def pe_machine(path: str | Path) -> int:
    """Read PE machine without loading code or requiring a .NET runtime."""
    import struct
    with Path(path).open('rb') as f:
        header = f.read(64)
        if len(header) != 64 or header[:2] != b'MZ':
            raise ValueError(f'Invalid PE DLL: {path}')
        offset = struct.unpack_from('<I', header, 60)[0]
        f.seek(offset)
        pe = f.read(6)
        if len(pe) != 6 or pe[:4] != b'PE\0\0':
            raise ValueError(f'Invalid PE DLL: {path}')
        return struct.unpack_from('<H', pe, 4)[0]


def require_x64_daq(path: str | Path) -> None:
    # NI DAQmx is mixed-mode/native, unlike AnyCPU pure-IL dependencies.
    machine = pe_machine(path)
    if machine != 0x8664:
        arch = '32-bit x86' if machine == 0x14c else hex(machine)
        raise RuntimeError(f'NI DAQmx DLL is {arch}, but Santec SDK requires 64-bit x64: {path}')


def installed_daq_candidates() -> list[Path]:
    """Bounded read-only search of the .NET Framework GAC, not the entire disk."""
    windows = Path(os.getenv('WINDIR', r'C:\Windows'))
    candidates = []
    for base in (windows / 'Microsoft.NET' / 'assembly', windows / 'assembly'):
        for arch in ('GAC_64', 'GAC_32', 'GAC_MSIL'):
            candidates.extend((base / arch / 'NationalInstruments.DAQmx').glob('*/NationalInstruments.DAQmx.dll'))
    return sorted(set(candidates))


def load_ni_daqmx():
    """Prefer an exact matching local DLL; otherwise use installed publisher policy.

    Never force-load the bundled x86 NI DLL into the x64 server. Do not silently
    redirect the SDK to an arbitrary newer major version/public key token.
    """
    import struct
    if struct.calcsize('P') != 8:
        raise RuntimeError('Santec SDK requires 64-bit Python; do not switch to 32-bit Python')
    override = os.getenv('SANTEC_NI_DAQMX_DLL')
    directory = Path(os.getenv('SANTEC_DLL_DIR') or DEFAULT_DLL_DIR).resolve()
    local = Path(override).resolve() if override else directory / 'NationalInstruments.DAQmx.dll'
    if local.exists():
        require_x64_daq(local)
    elif override:
        raise FileNotFoundError(f'Configured NI DLL does not exist: {local}')
    elif not any(pe_machine(p) == 0x8664 for p in installed_daq_candidates()):
        raise RuntimeError('No installed x64 NI-DAQmx .NET assembly or local matching DLL found. '
                           'Use the complete official-sdk server bundle or run diagnostics/diagnose_ni_install.py.')
    dll_dir = load_santec_dlls()
    import clr
    from System.Reflection import Assembly, AssemblyName

    sdk = clr.AddReference(str(dll_dir / 'Santec.Instrument.dll'))
    required = next(ref for ref in sdk.GetReferencedAssemblies()
                    if str(ref.Name) == 'NationalInstruments.DAQmx')
    if local.exists():
        identity = AssemblyName.GetAssemblyName(str(local))
        if str(identity.FullName) != str(required.FullName):
            raise RuntimeError(f'Local NI DLL identity does not match Santec SDK. Required: {required.FullName}; '
                               f'selected: {identity.FullName}. Use the matching official SDK bundle.')
        try:
            return clr.AddReference(str(local))
        except Exception as exc:
            raise RuntimeError(f'Matching x64 NI DLL found but could not load: {local}. '
                               f'Check NI native driver and dependent runtime components. Details: {exc}') from exc
    try:
        assembly = Assembly.Load(required)
        require_x64_daq(str(assembly.Location))
        # Register namespaces with pythonnet after the CLR resolves the SDK's identity.
        clr.AddReference(str(assembly.FullName))
        return assembly
    except Exception as exc:
        raise RuntimeError(
            f'Cannot load compatible x64 NI-DAQmx .NET runtime. Required by SDK: {required.FullName}. '
            'Install/repair NI-DAQmx .NET Framework support and its publisher policies; '
            'run python diagnostics/diagnose_daq.py and report its output. '
            f'Do not use the bundled x86 DAQmx DLL. Details: {exc}'
        ) from exc


def quarantine_x86_daq(directory: Path) -> None:
    """Reversibly hide the known incompatible DLL from pythonnet's resolver."""
    dll = directory / 'NationalInstruments.DAQmx.dll'
    if not dll.exists() or pe_machine(dll) != 0x14c:
        return
    backup = dll.with_name(dll.name + '.x86-disabled')
    index = 0
    while backup.exists():
        index += 1
        backup = dll.with_name(dll.name + f'.x86-disabled.{index}')
    try:
        dll.rename(backup)
    except OSError as exc:
        raise RuntimeError(f'Cannot quarantine incompatible x86 DLL {dll}. '
                           'Stop all Python server processes and rename this file to .x86-disabled.') from exc
    import logging
    logging.getLogger(__name__).warning('Disabled incompatible x86 NI DLL: %s -> %s', dll, backup)
