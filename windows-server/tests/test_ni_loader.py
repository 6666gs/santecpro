from pathlib import Path
import pytest
from santec_dll_backend import loader


def test_bundled_ni_and_santec_are_x64():
    root = Path(__file__).parents[1] / 'vendor' / 'santec_dll'
    assert loader.pe_machine(root / 'NationalInstruments.DAQmx.dll') == 0x8664
    assert loader.pe_machine(root / 'Santec.Instrument.dll') == 0x8664
    assert loader.pe_machine(root / 'STSProcess.dll') == 0x8664


def write_x86_stub(path):
    import struct
    data = bytearray(70)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 64)
    data[64:68] = b'PE\0\0'
    struct.pack_into('<H', data, 68, 0x14c)
    path.write_bytes(data)


def test_rejects_wrong_architecture_before_clr_load(tmp_path):
    dll = tmp_path/'x86.dll'
    write_x86_stub(dll)
    with pytest.raises(RuntimeError, match='32-bit'):
        loader.require_x64_daq(dll)


def test_invalid_pe_has_clear_error(tmp_path):
    file = tmp_path/'broken.dll'
    file.write_bytes(b'not a PE')
    with pytest.raises(ValueError, match='PE'):
        loader.pe_machine(file)


def test_uses_sdk_identity_and_installed_assembly(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    from unittest.mock import Mock
    required = SimpleNamespace(Name='NationalInstruments.DAQmx', FullName='DAQ SDK identity')
    installed = SimpleNamespace(FullName='DAQ installed identity', Location=str(tmp_path/'x64.dll'))
    sdk = SimpleNamespace(GetReferencedAssemblies=lambda: [required])
    clr = SimpleNamespace(AddReference=Mock(return_value=sdk))
    assembly = SimpleNamespace(Load=Mock(return_value=installed))
    monkeypatch.setitem(sys.modules, 'clr', clr)
    monkeypatch.setitem(sys.modules, 'System.Reflection', SimpleNamespace(Assembly=assembly, AssemblyName=Mock()))
    monkeypatch.setenv('SANTEC_DLL_DIR', str(tmp_path))
    monkeypatch.setattr(loader, 'load_santec_dlls', lambda: tmp_path)
    monkeypatch.setattr(loader, 'installed_daq_candidates', lambda: [tmp_path/'x64.dll'])
    monkeypatch.setattr(loader, 'pe_machine', lambda p: 0x8664)
    check = Mock()
    monkeypatch.setattr(loader, 'require_x64_daq', check)
    monkeypatch.delenv('SANTEC_NI_DAQMX_DLL', raising=False)
    assert loader.load_ni_daqmx() is installed
    assembly.Load.assert_called_once_with(required)
    check.assert_called_once_with(installed.Location)
    assert [c.args[0] for c in clr.AddReference.call_args_list] == [str(tmp_path/'Santec.Instrument.dll'), installed.FullName]


def test_installed_search_is_scoped_to_gac(monkeypatch, tmp_path):
    path=tmp_path/'Microsoft.NET'/'assembly'/'GAC_64'/'NationalInstruments.DAQmx'/'v4.0_version'/'NationalInstruments.DAQmx.dll'
    path.parent.mkdir(parents=True)
    path.touch()
    monkeypatch.setenv('WINDIR', str(tmp_path))
    assert loader.installed_daq_candidates() == [path]


def test_bad_daq_is_quarantined_without_overwriting_backup(tmp_path):
    import shutil
    source = Path(__file__).parents[1]/'vendor'/'santec_dll'/'NationalInstruments.DAQmx.dll'
    dll = tmp_path/source.name
    write_x86_stub(dll)
    original = dll.read_bytes()
    backup = tmp_path/(source.name+'.x86-disabled')
    backup.write_bytes(b'previous backup')
    loader.quarantine_x86_daq(tmp_path)
    assert not dll.exists()
    assert backup.read_bytes() == b'previous backup'
    assert (tmp_path/(source.name+'.x86-disabled.1')).read_bytes() == original


def test_missing_runtime_stops_before_loading_clr(monkeypatch, tmp_path):
    monkeypatch.setenv("SANTEC_DLL_DIR", str(tmp_path))
    from unittest.mock import Mock
    monkeypatch.setattr(loader, 'installed_daq_candidates', lambda: [])
    monkeypatch.delenv('SANTEC_NI_DAQMX_DLL', raising=False)
    load = Mock(side_effect=AssertionError('must not load CLR'))
    monkeypatch.setattr(loader, 'load_santec_dlls', load)
    with pytest.raises(RuntimeError, match='No installed x64'):
        loader.load_ni_daqmx()
    load.assert_not_called()


def test_matching_local_daq_loads_without_gac(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    from unittest.mock import Mock
    dll=tmp_path/'NationalInstruments.DAQmx.dll'
    dll.touch()
    required=SimpleNamespace(Name='NationalInstruments.DAQmx', FullName='DAQ exact identity')
    sdk=SimpleNamespace(GetReferencedAssemblies=lambda:[required])
    loaded=SimpleNamespace(FullName=required.FullName, Location=str(dll))
    clr=SimpleNamespace(AddReference=Mock(side_effect=[sdk,loaded]))
    assembly=SimpleNamespace(Load=Mock(side_effect=AssertionError('GAC must not be required')))
    names=SimpleNamespace(GetAssemblyName=Mock(return_value=required))
    monkeypatch.setitem(sys.modules,'clr',clr)
    monkeypatch.setitem(sys.modules,'System.Reflection',SimpleNamespace(Assembly=assembly,AssemblyName=names))
    monkeypatch.setenv('SANTEC_DLL_DIR',str(tmp_path))
    monkeypatch.delenv('SANTEC_NI_DAQMX_DLL',raising=False)
    monkeypatch.setattr(loader,'load_santec_dlls',lambda:tmp_path)
    monkeypatch.setattr(loader,'installed_daq_candidates',lambda:[])
    monkeypatch.setattr(loader,'require_x64_daq',lambda p:None)
    assert loader.load_ni_daqmx() is loaded
    assembly.Load.assert_not_called()
    names.GetAssemblyName.assert_called_once_with(str(dll))


@pytest.fixture
def fake_santec_loader(monkeypatch, tmp_path):
    """Exercise real initialization without CLR, NI drivers or hardware."""
    import sys
    from types import SimpleNamespace
    from unittest.mock import Mock
    for name in ('Santec.Instrument.dll', 'STSProcess.dll'):
        (tmp_path / name).touch()
    monkeypatch.setattr(loader.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(loader.os, 'pathsep', ';')
    monkeypatch.setattr(sys, 'path', list(sys.path))
    clr = SimpleNamespace(AddReference=Mock())
    monkeypatch.setitem(sys.modules, 'clr', clr)
    return tmp_path.resolve(), clr


def test_repeated_initialization_does_not_grow_search_paths(monkeypatch, fake_santec_loader):
    import sys
    directory, _ = fake_santec_loader
    original = r'C:\Windows\System32;C:\Other tools'
    monkeypatch.setenv('PATH', original)
    loader.load_santec_dlls(directory)
    expected_path, expected_sys_path = loader.os.environ['PATH'], list(sys.path)
    for _ in range(1000):
        assert loader.load_santec_dlls(directory) == directory
    assert loader.os.environ['PATH'] == expected_path == str(directory) + ';' + original
    assert sys.path == expected_sys_path


def test_repairs_existing_vendor_duplicates_only(monkeypatch, fake_santec_loader):
    directory, _ = fake_santec_loader
    variant = '"' + str(directory).upper().replace('/', '\\') + '\\"'
    # Simulate an old server's PATH approaching Windows' 32767-character limit.
    duplicates = [str(directory), variant] * (30000 // (2 * len(str(directory)) + 5))
    monkeypatch.setenv('PATH', ';'.join([r'C:\Other', *duplicates, '', r'C:\Other']))
    loader.load_santec_dlls(directory)
    assert loader.os.environ['PATH'] == str(directory) + r';C:\Other;;C:\Other'


def test_failed_clr_load_can_retry_without_path_growth(monkeypatch, fake_santec_loader):
    directory, clr = fake_santec_loader
    monkeypatch.setenv('PATH', r'C:\Windows')
    clr.AddReference.side_effect = RuntimeError('temporary load failure')
    with pytest.raises(RuntimeError, match='temporary'):
        loader.load_santec_dlls(directory)
    previous = loader.os.environ['PATH']
    clr.AddReference.side_effect = None
    assert loader.load_santec_dlls(directory) == directory
    assert loader.os.environ['PATH'] == previous


def test_concurrent_initialization_does_not_duplicate_path(monkeypatch, fake_santec_loader):
    from concurrent.futures import ThreadPoolExecutor
    directory, _ = fake_santec_loader
    monkeypatch.setenv('PATH', r'C:\Windows')
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(p == directory for p in pool.map(loader.load_santec_dlls, [directory] * 100))
    assert loader.os.environ['PATH'] == str(directory) + r';C:\Windows'
