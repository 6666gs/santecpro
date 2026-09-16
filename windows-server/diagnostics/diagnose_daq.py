"""List NI DAQ devices and SPU signatures; never starts acquisition/laser.

Run from windows-server: python diagnostics/diagnose_daq.py
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from santec_dll_backend.loader import (load_santec_dlls, load_ni_daqmx,
                                      pe_machine, installed_daq_candidates)


def main():
    import struct
    print(f'Python: {sys.executable} ({struct.calcsize("P") * 8}-bit)', flush=True)
    dll_dir = load_santec_dlls()
    for name in ('Santec.Instrument.dll', 'STSProcess.dll', 'NationalInstruments.DAQmx.dll'):
        path = dll_dir / name
        if path.exists():
            print(f'Bundled {name}: PE machine={hex(pe_machine(path))}', flush=True)
    print('Installed NI .NET assemblies (0x8664=x64, 0x14c=x86):', flush=True)
    for path in installed_daq_candidates():
        print(f'  {hex(pe_machine(path))}: {path}', flush=True)
    import clr
    from System.Reflection import AssemblyName
    for path in installed_daq_candidates():
        print(f'  Identity: {AssemblyName.GetAssemblyName(str(path)).FullName}', flush=True)
    assembly = load_ni_daqmx()
    print(f'Loaded: {assembly.FullName} from {assembly.Location}', flush=True)
    from NationalInstruments.DAQmx import DaqSystem
    from Santec import SPU
    devices = list(DaqSystem.Local.Devices)
    print(f'Configured DAQ: {config.DAQ_DEVICE!r}')
    print(f'NI MAX devices: {devices}')
    if config.DAQ_DEVICE not in devices:
        raise RuntimeError('Configured DAQ not found; check NI-DAQmx, USB cable and NI MAX device name')
    obj = SPU()
    names = {'Connect', 'Set_Sampling_Parameter', 'Sampling_Start',
             'Get_Sampling_Rawdata', 'Sampling_Stop'}
    for method in obj.GetType().GetMethods():
        if method.Name in names:
            print(method)
    print('Read-only check complete. No scan, sampling or laser command was issued.')


if __name__ == '__main__':
    main()
