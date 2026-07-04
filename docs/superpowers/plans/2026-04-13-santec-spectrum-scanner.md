# Santec Spectrum Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cross-platform pure-Python library to control Santec TSL-550 laser and MPM-210 power meter for wavelength scanning, multi-range data merging, and IL measurement, with real-time plotting and CSV export.

**Architecture:** PyVISA sends SCPI commands directly to instruments over GPIB. A `Scanner` coordinator synchronizes TSL sweeps with MPM logging. Multi-range data is merged in pure numpy. CSV export matches Santec STS software format.

**Tech Stack:** Python 3.10+, pyvisa, numpy, matplotlib

---

## File Structure

```
santecpro/
├── santecpro/
│   ├── __init__.py              # Package init, version, public API re-exports
│   ├── exceptions.py            # SantecError, InstrumentConnectionError, InstrumentOperationError
│   ├── instruments/
│   │   ├── __init__.py          # Re-export TSLInstrument, MPMInstrument
│   │   ├── base.py              # BaseInstrument (pyvisa wrapper)
│   │   ├── tsl.py               # TSLInstrument (TSL-550 SCPI control)
│   │   └── mpm.py               # MPMInstrument (MPM-210 SCPI control)
│   ├── scanner.py               # Scanner coordinator + ScanResult/ILMeasurement dataclasses
│   ├── plotter.py               # Real-time matplotlib plotting
│   └── exporter.py              # CSV export (raw + loss)
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures (mock pyvisa resources)
│   ├── test_base.py             # BaseInstrument tests
│   ├── test_tsl.py              # TSLInstrument tests
│   ├── test_mpm.py              # MPMInstrument tests
│   ├── test_scanner.py          # Scanner tests (merge, IL calc, sequence)
│   ├── test_exporter.py         # CSV export tests
│   └── test_plotter.py          # Plotter tests
├── examples/
│   └── basic_scan.py            # Usage example
├── pyproject.toml
└── requirements.txt
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `santecpro/__init__.py`
- Create: `santecpro/instruments/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=61.2"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "santecpro"
version = "1.0.0"
description = "Cross-platform Python driver for Santec TSL-550 laser and MPM-210 power meter"
requires-python = ">=3.10"
license = "MIT"
dependencies = [
    "pyvisa>=1.14",
    "numpy>=2.0",
    "matplotlib>=3.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create requirements.txt**

```
pyvisa>=1.14
numpy>=2.0
matplotlib>=3.9
```

- [ ] **Step 3: Create santecpro/__init__.py**

```python
"""Santecpro - Cross-platform Python driver for Santec instruments."""

__version__ = "1.0.0"
```

- [ ] **Step 4: Create santecpro/instruments/__init__.py**

```python
"""Santec instrument drivers."""
```

- [ ] **Step 5: Create tests/__init__.py**

Empty file.

- [ ] **Step 6: Create tests/conftest.py**

```python
"""Shared test fixtures for santecpro tests."""

import pytest
from unittest.mock import MagicMock, PropertyMock


@pytest.fixture
def mock_resource():
    """A mock pyvisa.Resource that records queries and writes."""
    resource = MagicMock()
    resource.query.side_effect = lambda cmd: {
        "*IDN?": "SANTEC,TSL-550,12345,1.00",
        "LD:STAT?": "ON",
        "SHUT?": "OPEN",
        "POW:LEV?": "5.000",
        "WAV?": "1550.000",
        "SWEEP:SPED?": "50.000",
        "SWEEP:STAT?": "STANDBY",
        ":READ:POIN?": "1000",
    }.get(cmd.upper(), "")
    resource.read.return_value = ""
    resource.write.return_value = None
    resource.timeout = 5000
    resource.query_delay = 0.0
    resource.write_termination = "\r"
    resource.read_termination = "\r"
    return resource


@pytest.fixture
def mock_resource_manager(mock_resource):
    """A mock pyvisa.ResourceManager that returns mock_resource."""
    rm = MagicMock()
    rm.open_resource.return_value = mock_resource
    return rm
```

- [ ] **Step 7: Commit**

```bash
git init
git add pyproject.toml requirements.txt santecpro/__init__.py santecpro/instruments/__init__.py tests/__init__.py tests/conftest.py
git commit -m "feat: project scaffolding with pyproject.toml and test fixtures"
```

---

### Task 2: Exceptions Module

**Files:**
- Create: `santecpro/exceptions.py`
- Create: `tests/test_exceptions.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_exceptions.py
"""Tests for santecpro.exceptions."""

import pytest
from santecpro.exceptions import (
    SantecError,
    InstrumentConnectionError,
    InstrumentOperationError,
)


def test_santec_error_has_message():
    err = SantecError("something broke")
    assert str(err) == "something broke"


def test_santec_error_has_error_code():
    err = SantecError("fail", error_code=-1)
    assert err.error_code == -1
    assert "fail" in str(err)


def test_santec_error_default_code():
    err = SantecError("fail")
    assert err.error_code is None


def test_connection_error_is_santec_error():
    err = InstrumentConnectionError("cannot connect")
    assert isinstance(err, SantecError)
    assert str(err) == "cannot connect"


def test_operation_error_is_santec_error():
    err = InstrumentOperationError("bad operation", error_code=-30)
    assert isinstance(err, SantecError)
    assert err.error_code == -30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_exceptions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'santecpro.exceptions'`

- [ ] **Step 3: Write the implementation**

```python
# santecpro/exceptions.py
"""Custom exceptions for santecpro."""


class SantecError(Exception):
    """Base exception for all santecpro errors."""

    def __init__(self, message: str, error_code: int | None = None):
        self.error_code = error_code
        super().__init__(message)


class InstrumentConnectionError(SantecError):
    """Raised when an instrument connection fails."""
    pass


class InstrumentOperationError(SantecError):
    """Raised when an instrument operation fails."""
    pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_exceptions.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add santecpro/exceptions.py tests/test_exceptions.py
git commit -m "feat: add exceptions module with SantecError hierarchy"
```

---

### Task 3: BaseInstrument

**Files:**
- Create: `santecpro/instruments/base.py`
- Create: `tests/test_base.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_base.py
"""Tests for santecpro.instruments.base."""

import pytest
from unittest.mock import MagicMock, patch, call
from santecpro.instruments.base import BaseInstrument
from santecpro.exceptions import InstrumentConnectionError


class TestBaseInstrument:
    def test_connect_opens_resource(self, mock_resource_manager):
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        mock_resource_manager.open_resource.assert_called_once_with("GPIB0::10::INSTR")

    def test_connect_sets_terminator(self, mock_resource_manager, mock_resource):
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        assert mock_resource.write_termination == "\r"
        assert mock_resource.read_termination == "\r"

    def test_connect_already_connected_raises(self, mock_resource_manager):
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        with pytest.raises(InstrumentConnectionError, match="already connected"):
            inst.connect("GPIB0::10::INSTR")

    def test_disconnect_closes_resource(self, mock_resource_manager, mock_resource):
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        inst.disconnect()
        mock_resource.close.assert_called_once()
        assert inst._resource is None

    def test_query_sends_command_and_returns_response(self, mock_resource_manager, mock_resource):
        mock_resource.query.return_value = "5.000"
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        result = inst.query("POW:LEV?")
        mock_resource.query.assert_called_once_with("POW:LEV?")
        assert result == "5.000"

    def test_write_sends_command(self, mock_resource_manager, mock_resource):
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        inst.write("POW:LEV 5")
        mock_resource.write.assert_called_with("POW:LEV 5")

    def test_read_returns_response(self, mock_resource_manager, mock_resource):
        mock_resource.read.return_value = "OK"
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        result = inst.read()
        assert result == "OK"

    def test_idn_returns_identity(self, mock_resource_manager, mock_resource):
        mock_resource.query.return_value = "SANTEC,TSL-550,12345,1.00"
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        assert inst.idn == "SANTEC,TSL-550,12345,1.00"
        mock_resource.query.assert_called_with("*IDN?")

    def test_timeout_property(self, mock_resource_manager, mock_resource):
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        assert inst.timeout == 5000
        inst.timeout = 10000
        assert mock_resource.timeout == 10000

    def test_query_when_not_connected_raises(self, mock_resource_manager):
        inst = BaseInstrument(mock_resource_manager)
        with pytest.raises(InstrumentConnectionError, match="not connected"):
            inst.query("*IDN?")

    def test_write_when_not_connected_raises(self, mock_resource_manager):
        inst = BaseInstrument(mock_resource_manager)
        with pytest.raises(InstrumentConnectionError, match="not connected"):
            inst.write("POW:LEV 5")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'santecpro.instruments.base'`

- [ ] **Step 3: Write the implementation**

```python
# santecpro/instruments/base.py
"""Base instrument class wrapping pyvisa communication."""

from __future__ import annotations

import pyvisa
from santecpro.exceptions import InstrumentConnectionError


class BaseInstrument:
    """Base class for all instrument drivers.

    Wraps a pyvisa ResourceManager and provides SCPI query/write/read
    methods. Subclasses add instrument-specific commands.
    """

    def __init__(self, resource_manager: pyvisa.ResourceManager | object):
        self._rm = resource_manager
        self._resource = None

    @property
    def is_connected(self) -> bool:
        return self._resource is not None

    def connect(self, resource_string: str, terminator: str = "\r") -> None:
        """Open a VISA resource and configure terminator."""
        if self._resource is not None:
            raise InstrumentConnectionError(
                f"Already connected. Disconnect first. Resource: {resource_string}"
            )
        try:
            self._resource = self._rm.open_resource(resource_string)
        except Exception as exc:
            raise InstrumentConnectionError(
                f"Failed to connect to {resource_string}: {exc}"
            ) from exc
        self._resource.write_termination = terminator
        self._resource.read_termination = terminator

    def disconnect(self) -> None:
        """Close the VISA resource."""
        if self._resource is not None:
            self._resource.close()
            self._resource = None

    def _require_connected(self) -> None:
        if self._resource is None:
            raise InstrumentConnectionError("Not connected. Call connect() first.")

    def query(self, command: str) -> str:
        """Send a SCPI query and return the response string."""
        self._require_connected()
        return self._resource.query(command)

    def write(self, command: str) -> None:
        """Send a SCPI command (no response expected)."""
        self._require_connected()
        self._resource.write(command)

    def read(self) -> str:
        """Read a response from the instrument."""
        self._require_connected()
        return self._resource.read()

    @property
    def idn(self) -> str:
        """Return the instrument identification string (*IDN?)."""
        return self.query("*IDN?")

    @property
    def timeout(self) -> int:
        """Return the VISA timeout in milliseconds."""
        self._require_connected()
        return self._resource.timeout

    @timeout.setter
    def timeout(self, value: int) -> None:
        self._require_connected()
        self._resource.timeout = value
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_base.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add santecpro/instruments/base.py tests/test_base.py
git commit -m "feat: add BaseInstrument with pyvisa wrapper"
```

---

### Task 4: TSLInstrument

**Files:**
- Create: `santecpro/instruments/tsl.py`
- Create: `tests/test_tsl.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_tsl.py
"""Tests for santecpro.instruments.tsl."""

import pytest
from unittest.mock import MagicMock, call
from santecpro.instruments.tsl import TSLInstrument
from santecpro.exceptions import InstrumentConnectionError


@pytest.fixture
def tsl(mock_resource_manager, mock_resource):
    inst = TSLInstrument(mock_resource_manager)
    inst.connect("GPIB0::10::INSTR")
    return inst


class TestTSLConnection:
    def test_connect_sends_init_sequence(self, mock_resource):
        rm = MagicMock()
        rm.open_resource.return_value = mock_resource
        inst = TSLInstrument(rm)
        inst.connect("GPIB0::10::INSTR")
        mock_resource.write.assert_any_call("*CLS")
        mock_resource.write.assert_any_call("*RST")


class TestTSLLaserControl:
    def test_laser_on(self, tsl, mock_resource):
        tsl.laser_on()
        mock_resource.write.assert_called_with("LD:STAT ON")

    def test_laser_off(self, tsl, mock_resource):
        tsl.laser_off()
        mock_resource.write.assert_called_with("LD:STAT OFF")

    def test_get_laser_status(self, tsl, mock_resource):
        mock_resource.query.return_value = "ON"
        assert tsl.get_laser_status() == "ON"
        mock_resource.query.assert_called_with("LD:STAT?")

    def test_shutter_open(self, tsl, mock_resource):
        tsl.shutter_open()
        mock_resource.write.assert_called_with("SHUT ON")

    def test_shutter_close(self, tsl, mock_resource):
        tsl.shutter_close()
        mock_resource.write.assert_called_with("SHUT OFF")

    def test_get_shutter_status(self, tsl, mock_resource):
        mock_resource.query.return_value = "OPEN"
        assert tsl.get_shutter_status() == "OPEN"
        mock_resource.query.assert_called_with("SHUT?")


class TestTSLPowerWavelength:
    def test_set_power(self, tsl, mock_resource):
        tsl.set_power(5.0)
        mock_resource.write.assert_called_with("POW:LEV 5.000000")

    def test_get_power(self, tsl, mock_resource):
        mock_resource.query.return_value = "5.000"
        assert tsl.get_power() == 5.0
        mock_resource.query.assert_called_with("POW:LEV?")

    def test_set_wavelength(self, tsl, mock_resource):
        tsl.set_wavelength(1550.0)
        mock_resource.write.assert_called_with("WAV 1550.000000")

    def test_get_wavelength(self, tsl, mock_resource):
        mock_resource.query.return_value = "1550.000"
        assert tsl.get_wavelength() == 1550.0
        mock_resource.query.assert_called_with("WAV?")


class TestTSLSweep:
    def test_set_sweep_mode(self, tsl, mock_resource):
        tsl.set_sweep_mode("CONT_ONEWAY")
        mock_resource.write.assert_called_with("SWEEP:MODE CONT_ONEWAY")

    def test_set_sweep_speed(self, tsl, mock_resource):
        tsl.set_sweep_speed(50.0)
        mock_resource.write.assert_called_with("SWEEP:SPED 50.000000")

    def test_get_sweep_speed(self, tsl, mock_resource):
        mock_resource.query.return_value = "50.000"
        assert tsl.get_sweep_speed() == 50.0

    def test_set_sweep_start(self, tsl, mock_resource):
        tsl.set_sweep_start(1500.0)
        mock_resource.write.assert_called_with("SWEEP:STAR:WAV 1500.000000")

    def test_set_sweep_stop(self, tsl, mock_resource):
        tsl.set_sweep_stop(1630.0)
        mock_resource.write.assert_called_with("SWEEP:STOP:WAV 1630.000000")

    def test_set_sweep_step(self, tsl, mock_resource):
        tsl.set_sweep_step(0.001)
        mock_resource.write.assert_called_with("SWEEP:STEP 0.001000")

    def test_start_sweep(self, tsl, mock_resource):
        tsl.start_sweep()
        mock_resource.write.assert_called_with("SWEEP:STAT START")

    def test_stop_sweep(self, tsl, mock_resource):
        tsl.stop_sweep()
        mock_resource.write.assert_called_with("SWEEP:STAT STOP")

    def test_pause_sweep(self, tsl, mock_resource):
        tsl.pause_sweep()
        mock_resource.write.assert_called_with("SWEEP:STAT PAUSE")

    def test_restart_sweep(self, tsl, mock_resource):
        tsl.restart_sweep()
        mock_resource.write.assert_called_with("SWEEP:STAT REST")

    def test_get_sweep_status(self, tsl, mock_resource):
        mock_resource.query.return_value = "STANDBY"
        assert tsl.get_sweep_status() == "STANDBY"

    def test_soft_trigger(self, tsl, mock_resource):
        tsl.soft_trigger()
        mock_resource.write.assert_called_with("TRIG:SOFT")

    def test_set_trigger_output(self, tsl, mock_resource):
        tsl.set_trigger_output("STEP")
        mock_resource.write.assert_called_with("TRIG:OUTP STEP")

    def test_set_scan_start_mode(self, tsl, mock_resource):
        tsl.set_scan_start_mode("WAITING_FOR_TRIGGER")
        mock_resource.write.assert_called_with("SWEEP:STAR:MOD WAITING_FOR_TRIGGER")

    def test_status_clear(self, tsl, mock_resource):
        tsl.status_clear()
        mock_resource.write.assert_called_with("*CLS")

    def test_device_reset(self, tsl, mock_resource):
        tsl.device_reset()
        mock_resource.write.assert_called_with("*RST")

    def test_get_logging_data_points(self, tsl, mock_resource):
        mock_resource.query.return_value = "1000"
        assert tsl.get_logging_data_points() == 1000
        mock_resource.query.assert_called_with(":READ:POIN?")

    def test_get_power_monitor_data(self, tsl, mock_resource):
        mock_resource.query.return_value = "7.58,7.59,7.60"
        result = tsl.get_power_monitor_data()
        assert len(result) == 3
        assert result[0] == pytest.approx(7.58)

    def test_configure_sweep_sets_all_params(self, tsl, mock_resource):
        tsl.configure_sweep(
            start_wl=1500.0, stop_wl=1630.0, step=0.001, speed=20.0
        )
        calls = mock_resource.write.call_args_list
        written = [c[0][0] for c in calls]
        assert "SWEEP:STAR:WAV 1500.000000" in written
        assert "SWEEP:STOP:WAV 1630.000000" in written
        assert "SWEEP:STEP 0.001000" in written
        assert "SWEEP:SPED 20.000000" in written
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_tsl.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'santecpro.instruments.tsl'`

- [ ] **Step 3: Write the implementation**

```python
# santecpro/instruments/tsl.py
"""TSL-550 Tunable Laser instrument driver."""

from __future__ import annotations

from santecpro.instruments.base import BaseInstrument


class TSLInstrument(BaseInstrument):
    """Driver for the Santec TSL-550 tunable laser source.

    Communicates via SCPI commands over GPIB/LAN/USB (pyvisa).
    """

    def connect(self, resource_string: str) -> None:
        """Connect to TSL and send initialization sequence."""
        super().connect(resource_string, terminator="\r")
        self.status_clear()
        self.device_reset()

    # --- Laser diode control ---

    def laser_on(self) -> None:
        self.write("LD:STAT ON")

    def laser_off(self) -> None:
        self.write("LD:STAT OFF")

    def get_laser_status(self) -> str:
        return self.query("LD:STAT?")

    # --- Shutter control ---

    def shutter_open(self) -> None:
        self.write("SHUT ON")

    def shutter_close(self) -> None:
        self.write("SHUT OFF")

    def get_shutter_status(self) -> str:
        return self.query("SHUT?")

    # --- Power control ---

    def set_power(self, power_dbm: float) -> None:
        self.write(f"POW:LEV {power_dbm:.6f}")

    def get_power(self) -> float:
        return float(self.query("POW:LEV?"))

    # --- Wavelength control ---

    def set_wavelength(self, wl_nm: float) -> None:
        self.write(f"WAV {wl_nm:.6f}")

    def get_wavelength(self) -> float:
        return float(self.query("WAV?"))

    # --- Sweep configuration ---

    def set_sweep_mode(self, mode: str) -> None:
        """Set sweep mode: CONT_ONEWAY, CONT_TWOWAY, STEP_ONEWAY, STEP_TWOWAY."""
        self.write(f"SWEEP:MODE {mode}")

    def set_sweep_speed(self, speed: float) -> None:
        """Set sweep speed in nm/s."""
        self.write(f"SWEEP:SPED {speed:.6f}")

    def get_sweep_speed(self) -> float:
        return float(self.query("SWEEP:SPED?"))

    def set_sweep_start(self, wl: float) -> None:
        """Set sweep start wavelength in nm."""
        self.write(f"SWEEP:STAR:WAV {wl:.6f}")

    def set_sweep_stop(self, wl: float) -> None:
        """Set sweep stop wavelength in nm."""
        self.write(f"SWEEP:STOP:WAV {wl:.6f}")

    def set_sweep_step(self, step: float) -> None:
        """Set sweep step in nm."""
        self.write(f"SWEEP:STEP {step:.6f}")

    # --- Sweep execution ---

    def start_sweep(self) -> None:
        self.write("SWEEP:STAT START")

    def stop_sweep(self) -> None:
        self.write("SWEEP:STAT STOP")

    def pause_sweep(self) -> None:
        self.write("SWEEP:STAT PAUSE")

    def restart_sweep(self) -> None:
        self.write("SWEEP:STAT REST")

    def get_sweep_status(self) -> str:
        return self.query("SWEEP:STAT?")

    def soft_trigger(self) -> None:
        self.write("TRIG:SOFT")

    # --- Trigger configuration ---

    def set_trigger_output(self, mode: str) -> None:
        """Set trigger output mode: NONE, STOP, START, STEP."""
        self.write(f"TRIG:OUTP {mode}")

    def set_scan_start_mode(self, mode: str) -> None:
        """Set scan start mode: NORMAL, WAITING_FOR_TRIGGER."""
        self.write(f"SWEEP:STAR:MOD {mode}")

    # --- Utility ---

    def status_clear(self) -> None:
        self.write("*CLS")

    def device_reset(self) -> None:
        self.write("*RST")

    def get_logging_data_points(self) -> int:
        """Get number of logged data points."""
        return int(self.query(":READ:POIN?"))

    def get_power_monitor_data(self) -> list[float]:
        """Read TSL power monitor log data as a list of floats."""
        raw = self.query(":READ:POW?")
        return [float(v) for v in raw.split(",") if v.strip()]

    def configure_sweep(
        self, start_wl: float, stop_wl: float, step: float, speed: float
    ) -> None:
        """Convenience method to set all sweep parameters at once."""
        self.set_sweep_start(start_wl)
        self.set_sweep_stop(stop_wl)
        self.set_sweep_step(step)
        self.set_sweep_speed(speed)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_tsl.py -v`
Expected: 24 passed

- [ ] **Step 5: Commit**

```bash
git add santecpro/instruments/tsl.py tests/test_tsl.py
git commit -m "feat: add TSLInstrument with SCPI commands for TSL-550"
```

---

### Task 5: MPMInstrument

**Files:**
- Create: `santecpro/instruments/mpm.py`
- Create: `tests/test_mpm.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_mpm.py
"""Tests for santecpro.instruments.mpm."""

import pytest
from unittest.mock import MagicMock
from santecpro.instruments.mpm import MPMInstrument, MPM_RANGES


@pytest.fixture
def mpm(mock_resource_manager, mock_resource):
    inst = MPMInstrument(mock_resource_manager)
    inst.connect("GPIB0::17::INSTR")
    return inst


class TestMPMRanges:
    def test_mpm_ranges_constant(self):
        assert MPM_RANGES == {
            1: (-30, 10),
            2: (-40, 0),
            3: (-50, -10),
            4: (-60, -20),
            5: (-80, -30),
        }


class TestMPMConnection:
    def test_connect_sets_lf_terminator(self, mock_resource):
        rm = MagicMock()
        rm.open_resource.return_value = mock_resource
        inst = MPMInstrument(rm)
        inst.connect("GPIB0::17::INSTR")
        assert mock_resource.write_termination == "\n"
        assert mock_resource.read_termination == "\n"


class TestMPMBasicControl:
    def test_set_wavelength(self, mpm, mock_resource):
        mpm.set_wavelength(1550.0)
        mock_resource.write.assert_called_with("WAV 1550.000000")

    def test_set_range(self, mpm, mock_resource):
        mpm.set_range(2)
        mock_resource.write.assert_called_with("RANG 2")

    def test_set_range_mode_manual(self, mpm, mock_resource):
        mpm.set_range_mode("MANUAL")
        mock_resource.write.assert_called_with("RANG:MOD MANUAL")

    def test_set_range_mode_auto(self, mpm, mock_resource):
        mpm.set_range_mode("AUTO")
        mock_resource.write.assert_called_with("RANG:MOD AUTO")

    def test_set_averaging_time(self, mpm, mock_resource):
        mpm.set_averaging_time(0.00005)
        mock_resource.write.assert_called_with("AVG 0.000050")

    def test_get_averaging_time(self, mpm, mock_resource):
        mock_resource.query.return_value = "0.000050"
        assert mpm.get_averaging_time() == pytest.approx(5e-5)

    def test_set_unit(self, mpm, mock_resource):
        mpm.set_unit("dBm")
        mock_resource.write.assert_called_with("POW:UNIT dBm")

    def test_get_power(self, mpm, mock_resource):
        mock_resource.query.return_value = "-33.268"
        assert mpm.get_power(channel=1) == pytest.approx(-33.268)
        mock_resource.query.assert_called_with("READ:POW:CH1?")


class TestMPMLogging:
    def test_set_logging_data_points(self, mpm, mock_resource):
        mpm.set_logging_data_points(130001)
        mock_resource.write.assert_called_with("LOGG:POIN 130001")

    def test_start_logging(self, mpm, mock_resource):
        mpm.start_logging()
        mock_resource.write.assert_called_with("LOGG:STAT START")

    def test_stop_logging(self, mpm, mock_resource):
        mpm.stop_logging()
        mock_resource.write.assert_called_with("LOGG:STAT STOP")

    def test_get_logging_status(self, mpm, mock_resource):
        mock_resource.query.return_value = "0,50000"
        status, count = mpm.get_logging_status()
        assert status == 0
        assert count == 50000
        mock_resource.query.assert_called_with("LOGG:STAT?")

    def test_get_channel_logging_data(self, mpm, mock_resource):
        mock_resource.query.return_value = "-33.268,-33.280,-33.275"
        data = mpm.get_channel_logging_data(module=1, channel=1)
        assert len(data) == 3
        assert data[0] == pytest.approx(-33.268)
        mock_resource.query.assert_called_with("LOGG:CH1:DATA?")


class TestMPMMisc:
    def test_perform_zeroing(self, mpm, mock_resource):
        mpm.perform_zeroing()
        mock_resource.write.assert_called_with("ZERO")

    def test_set_measurement_mode(self, mpm, mock_resource):
        mpm.set_measurement_mode("SWEEP1")
        mock_resource.write.assert_called_with("MOD SWEEP1")

    def test_set_trigger_input(self, mpm, mock_resource):
        mpm.set_trigger_input("EXTERNAL")
        mock_resource.write.assert_called_with("TRIG:INP EXTERNAL")

    def test_select_optimal_range_high_power(self, mpm):
        assert mpm.select_optimal_range(5.0) == 1

    def test_select_optimal_range_medium_power(self, mpm):
        assert mpm.select_optimal_range(-25.0) == 1

    def test_select_optimal_range_low_power(self, mpm):
        assert mpm.select_optimal_range(-35.0) == 2

    def test_select_optimal_range_very_low_power(self, mpm):
        assert mpm.select_optimal_range(-55.0) == 3

    def test_select_optimal_range_ultra_low_power(self, mpm):
        assert mpm.select_optimal_range(-65.0) == 4

    def test_select_optimal_range_extremely_low_power(self, mpm):
        assert mpm.select_optimal_range(-75.0) == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_mpm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'santecpro.instruments.mpm'`

- [ ] **Step 3: Write the implementation**

```python
# santecpro/instruments/mpm.py
"""MPM-210 Multi-Channel Power Meter instrument driver."""

from __future__ import annotations

from santecpro.instruments.base import BaseInstrument

# MPM-211 module dynamic ranges: range_number -> (min_dBm, max_dBm)
MPM_RANGES: dict[int, tuple[float, float]] = {
    1: (-30, 10),
    2: (-40, 0),
    3: (-50, -10),
    4: (-60, -20),
    5: (-80, -30),
}


class MPMInstrument(BaseInstrument):
    """Driver for the Santec MPM-210 multi-channel power meter.

    Communicates via SCPI commands over GPIB/LAN/USB (pyvisa).
    """

    def connect(self, resource_string: str) -> None:
        """Connect to MPM with LF terminator."""
        super().connect(resource_string, terminator="\n")

    # --- Wavelength ---

    def set_wavelength(self, wl_nm: float) -> None:
        self.write(f"WAV {wl_nm:.6f}")

    # --- Range control ---

    def set_range(self, range_val: int) -> None:
        """Set power range (1-5)."""
        self.write(f"RANG {range_val}")

    def set_range_mode(self, mode: str) -> None:
        """Set range mode: MANUAL or AUTO."""
        self.write(f"RANG:MOD {mode}")

    def set_range_per_channel(self, channel: int, range_val: int) -> None:
        self.write(f"RANG:CH{channel} {range_val}")

    # --- Averaging ---

    def set_averaging_time(self, time: float) -> None:
        self.write(f"AVG {time:.6f}")

    def get_averaging_time(self) -> float:
        return float(self.query("AVG?"))

    # --- Unit ---

    def set_unit(self, unit: str) -> None:
        """Set power unit: dBm or mW."""
        self.write(f"POW:UNIT {unit}")

    # --- Power reading ---

    def get_power(self, channel: int) -> float:
        return float(self.query(f"READ:POW:CH{channel}?"))

    # --- Logging ---

    def set_logging_data_points(self, n: int) -> None:
        self.write(f"LOGG:POIN {n}")

    def start_logging(self) -> None:
        self.write("LOGG:STAT START")

    def stop_logging(self) -> None:
        self.write("LOGG:STAT STOP")

    def get_logging_status(self) -> tuple[int, int]:
        """Return (status, count). status: -1=stopped, 0=logging, 1=completed."""
        raw = self.query("LOGG:STAT?")
        parts = raw.split(",")
        return int(parts[0]), int(parts[1])

    def get_channel_logging_data(self, module: int, channel: int) -> list[float]:
        """Retrieve logged power data for a specific module/channel."""
        raw = self.query(f"LOGG:CH{channel}:DATA?")
        return [float(v) for v in raw.split(",") if v.strip()]

    def get_module_logging_data(self, module: int) -> list[list[float]]:
        """Retrieve logged data for all channels of a module."""
        raw = self.query(f"LOGG:MOD{module}:DATA?")
        rows = raw.split(";")
        return [[float(v) for v in row.split(",") if v.strip()] for row in rows if row.strip()]

    # --- Zeroing ---

    def perform_zeroing(self) -> None:
        self.write("ZERO")

    # --- Measurement mode ---

    def set_measurement_mode(self, mode: str) -> None:
        """Set measurement mode: SWEEP1, SWEEP2, FREERUN."""
        self.write(f"MOD {mode}")

    # --- Trigger ---

    def set_trigger_input(self, mode: str) -> None:
        """Set trigger input: INTERNAL or EXTERNAL."""
        self.write(f"TRIG:INP {mode}")

    # --- Helpers ---

    def select_optimal_range(self, power_dbm: float) -> int:
        """Select the optimal MPM range for a given power level.

        Picks the lowest range number (highest sensitivity) whose dynamic
        range still covers the given power.
        """
        for range_num in sorted(MPM_RANGES.keys()):
            min_p, max_p = MPM_RANGES[range_num]
            if min_p <= power_dbm <= max_p:
                return range_num
        # If power exceeds all ranges, use range 1 (highest power range)
        return 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_mpm.py -v`
Expected: 20 passed

- [ ] **Step 5: Update instruments/__init__.py**

```python
# santecpro/instruments/__init__.py
"""Santec instrument drivers."""

from santecpro.instruments.tsl import TSLInstrument
from santecpro.instruments.mpm import MPMInstrument

__all__ = ["TSLInstrument", "MPMInstrument"]
```

- [ ] **Step 6: Commit**

```bash
git add santecpro/instruments/mpm.py santecpro/instruments/__init__.py tests/test_mpm.py
git commit -m "feat: add MPMInstrument with SCPI commands for MPM-210"
```

---

### Task 6: Scanner — ScanResult, merge, and IL calculation

**Files:**
- Create: `santecpro/scanner.py` (data classes + pure algorithm methods)
- Create: `tests/test_scanner.py` (unit tests for merge and IL)

- [ ] **Step 1: Write the test**

```python
# tests/test_scanner.py
"""Tests for santecpro.scanner — merge algorithm and IL calculation."""

import numpy as np
import numpy.testing as npt
import pytest
from santecpro.scanner import ScanResult, merge_multi_range, calculate_il


def _make_scan(wavelengths, powers, monitor_powers=None, mpm_range=1):
    if monitor_powers is None:
        monitor_powers = np.full_like(powers, 7.5)
    return ScanResult(
        wavelengths=np.array(wavelengths, dtype=float),
        powers=np.array(powers, dtype=float),
        monitor_powers=np.array(monitor_powers, dtype=float),
        scan_params={},
        timestamp="2026-04-13T00:00:00",
        mpm_range=mpm_range,
    )


class TestMergeMultiRange:
    def test_single_range_passes_through(self):
        scan = _make_scan([1500, 1510, 1520], [-10, -20, -30], mpm_range=1)
        merged = merge_multi_range([scan])
        npt.assert_array_equal(merged.powers, scan.powers)
        npt.assert_array_equal(merged.wavelengths, scan.wavelengths)

    def test_two_ranges_overlap_picks_best(self):
        # Range 1: valid -30..+10, signal -5 everywhere
        scan1 = _make_scan([1500, 1510, 1520], [-5, -5, -5], mpm_range=1)
        # Range 3: valid -50..-10, signal also shows -5 but range 1 is better
        scan3 = _make_scan([1500, 1510, 1520], [-5, -5, -5], mpm_range=3)
        merged = merge_multi_range([scan1, scan3])
        # Both are valid; prefer lowest range number (range 1)
        npt.assert_array_equal(merged.powers, [-5, -5, -5])
        assert merged.mpm_range == 0

    def test_two_ranges_stitch_together(self):
        # Range 1 valid: -30..+10
        # Range 3 valid: -50..-10
        # At 1500nm: -5 dBm (range 1 valid)
        # At 1510nm: -35 dBm (only range 3 valid)
        # At 1520nm: -25 dBm (range 1 valid)
        scan1 = _make_scan([1500, 1510, 1520], [-5, -35, -25], mpm_range=1)
        scan3 = _make_scan([1500, 1510, 1520], [-5, -35, -25], mpm_range=3)
        merged = merge_multi_range([scan1, scan3])
        assert merged.powers[0] == pytest.approx(-5)    # range 1 (lower number)
        assert merged.powers[1] == pytest.approx(-35)   # only range 3 valid
        assert merged.powers[2] == pytest.approx(-25)   # range 1 (lower number)

    def test_gap_produces_nan(self):
        scan1 = _make_scan([1500, 1510, 1520], [-5, -45, -25], mpm_range=1)
        # At 1510nm: -45 dBm is outside range 1 (-30..+10)
        # No other range provided, so NaN
        merged = merge_multi_range([scan1])
        assert np.isnan(merged.powers[1])

    def test_merged_uses_first_wavelength_grid(self):
        scan1 = _make_scan([1500, 1510, 1520], [-5, -5, -5], mpm_range=1)
        scan3 = _make_scan([1500, 1510, 1520], [-5, -5, -5], mpm_range=3)
        merged = merge_multi_range([scan1, scan3])
        npt.assert_array_equal(merged.wavelengths, scan1.wavelengths)


class TestCalculateIL:
    def test_basic_il(self):
        ref = _make_scan([1500, 1510, 1520], [-10, -10, -10])
        meas = _make_scan([1500, 1510, 1520], [-15, -15, -15])
        il = calculate_il(ref, meas)
        npt.assert_allclose(il, [5.0, 5.0, 5.0])

    def test_il_with_monitor_subtraction(self):
        # IL = (monitor_ref - mpm_ref) - (monitor_meas - mpm_meas)
        # Or equivalently: IL = (mpm_ref - mpm_meas) when monitors match
        ref = _make_scan([1500, 1510], [-10, -10], [7.5, 7.5])
        meas = _make_scan([1500, 1510], [-20, -25], [7.5, 7.5])
        il = calculate_il(ref, meas)
        npt.assert_allclose(il, [10.0, 15.0])

    def test_il_with_different_wavelength_grids_interpolates(self):
        ref = _make_scan([1500, 1510, 1520], [-10, -15, -20])
        meas = _make_scan([1500, 1505, 1510, 1515, 1520], [-10, -12, -15, -18, -20])
        il = calculate_il(ref, meas)
        assert len(il) == len(meas.wavelengths)
        # At 1500: ref=-10, meas=-10 -> IL=0
        assert il[0] == pytest.approx(0.0)
        # At 1520: ref=-20, meas=-20 -> IL=0
        assert il[-1] == pytest.approx(0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_scanner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'santecpro.scanner'`

- [ ] **Step 3: Write the implementation**

```python
# santecpro/scanner.py
"""Scan coordinator: data classes, merge algorithm, and IL calculation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from santecpro.instruments.mpm import MPM_RANGES


@dataclass
class ScanResult:
    """Result of a single wavelength scan."""

    wavelengths: np.ndarray      # nm
    powers: np.ndarray           # dBm (MPM measured)
    monitor_powers: np.ndarray   # dBm (TSL power monitor)
    scan_params: dict            # Full parameter record
    timestamp: str               # ISO format
    mpm_range: int               # MPM range used (0 for merged)


@dataclass
class ILMeasurement:
    """Result of a full IL measurement (reference + DUT)."""

    reference: ScanResult
    measurement: ScanResult      # merged multi-range result
    il: np.ndarray               # IL in dB
    wavelengths: np.ndarray      # nm


def merge_multi_range(scan_results: list[ScanResult]) -> ScanResult:
    """Merge multi-range scan data into a single wide-dynamic-range curve.

    For each wavelength point, select data from the range where the signal
    is within the valid dynamic range. If multiple ranges are valid, prefer
    the lowest range number (highest signal, best SNR).
    """
    if len(scan_results) == 1:
        return scan_results[0]

    # Use wavelength grid from first scan (all should be identical)
    wavelengths = scan_results[0].wavelengths.copy()
    merged_powers = np.full(len(wavelengths), np.nan)
    merged_monitor = np.full(len(wavelengths), np.nan)

    # Sort by range number (ascending) so lowest range gets priority
    sorted_scans = sorted(scan_results, key=lambda s: s.mpm_range)

    # Iterate in reverse: highest range first, then overwrite with lower ranges
    # This ensures lowest valid range wins
    for scan in reversed(sorted_scans):
        min_p, max_p = MPM_RANGES[scan.mpm_range]
        valid_mask = (scan.powers >= min_p) & (scan.powers <= max_p)
        merged_powers[valid_mask] = scan.powers[valid_mask]
        merged_monitor[valid_mask] = scan.monitor_powers[valid_mask]

    return ScanResult(
        wavelengths=wavelengths,
        powers=merged_powers,
        monitor_powers=merged_monitor,
        scan_params=scan_results[0].scan_params.copy(),
        timestamp=datetime.now().isoformat(),
        mpm_range=0,
    )


def calculate_il(reference: ScanResult, measurement: ScanResult) -> np.ndarray:
    """Calculate insertion loss: IL(λ) = P_ref(λ) - P_meas(λ).

    If wavelength grids differ, interpolate reference onto measurement grid.
    """
    if np.array_equal(reference.wavelengths, measurement.wavelengths):
        return reference.powers - measurement.powers

    ref_interp = np.interp(
        measurement.wavelengths,
        reference.wavelengths,
        reference.powers,
    )
    return ref_interp - measurement.powers
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_scanner.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add santecpro/scanner.py tests/test_scanner.py
git commit -m "feat: add ScanResult, merge_multi_range, and calculate_il"
```

---

### Task 7: Scanner — Coordinator class

**Files:**
- Modify: `santecpro/scanner.py` (add Scanner class)
- Modify: `tests/test_scanner.py` (add Scanner sequence tests)

This task adds the `Scanner` class that orchestrates the actual instrument communication. Tests use mock instruments.

- [ ] **Step 1: Write the Scanner sequence tests**

Append these tests to `tests/test_scanner.py`:

```python
from unittest.mock import MagicMock, patch, PropertyMock
from santecpro.scanner import Scanner, ILMeasurement
from santecpro.instruments.tsl import TSLInstrument
from santecpro.instruments.mpm import MPMInstrument


def _make_mock_tsl():
    tsl = MagicMock(spec=TSLInstrument)
    tsl.is_connected = True
    tsl.idn = "SANTEC,TSL-550,12345,1.00"
    tsl.get_sweep_status.return_value = "STANDING_BY_TRIGGER"
    tsl.get_logging_data_points.return_value = 5
    tsl.get_power_monitor_data.return_value = [7.5, 7.6, 7.7, 7.8, 7.9]
    return tsl


def _make_mock_mpm():
    mpm = MagicMock(spec=MPMInstrument)
    mpm.is_connected = True
    mpm.idn = "SANTEC,MPM-210,67890,1.16"
    mpm.get_logging_status.return_value = (1, 5)
    mpm.get_channel_logging_data.return_value = [-10.0, -11.0, -12.0, -13.0, -14.0]
    mpm.get_power.return_value = -10.0
    return mpm


class TestScannerConfigure:
    def test_configure_stores_params(self):
        tsl = _make_mock_tsl()
        mpm = _make_mock_mpm()
        scanner = Scanner(tsl, mpm)
        scanner.configure(
            start_wl=1500.0, stop_wl=1630.0, step=0.001,
            speed=20.0, power=5.0
        )
        assert scanner._config["start_wl"] == 1500.0
        assert scanner._config["stop_wl"] == 1630.0
        assert scanner._config["step"] == 0.001
        assert scanner._config["speed"] == 20.0
        assert scanner._config["power"] == 5.0

    def test_configure_calls_tsl(self):
        tsl = _make_mock_tsl()
        mpm = _make_mock_mpm()
        scanner = Scanner(tsl, mpm)
        scanner.configure(
            start_wl=1500.0, stop_wl=1630.0, step=0.001,
            speed=20.0, power=5.0
        )
        tsl.configure_sweep.assert_called_once_with(1500.0, 1630.0, 0.001, 20.0)
        tsl.set_power.assert_called_once_with(5.0)
        tsl.set_trigger_output.assert_called_once_with("STEP")

    def test_configure_calls_mpm(self):
        tsl = _make_mock_tsl()
        mpm = _make_mock_mpm()
        scanner = Scanner(tsl, mpm)
        scanner.configure(
            start_wl=1500.0, stop_wl=1630.0, step=0.001,
            speed=20.0, power=5.0, ranges=[1, 3]
        )
        mpm.set_range_mode.assert_called_with("MANUAL")


class TestScannerRunSingleScan:
    def test_single_scan_returns_scan_result(self):
        tsl = _make_mock_tsl()
        mpm = _make_mock_mpm()
        scanner = Scanner(tsl, mpm)
        scanner.configure(
            start_wl=1500.0, stop_wl=1500.004, step=0.001,
            speed=20.0, power=5.0
        )
        result = scanner.run_single_scan(mpm_range=1, plot=False)
        assert isinstance(result, ScanResult)
        assert len(result.wavelengths) == 5
        assert len(result.powers) == 5
        assert result.mpm_range == 1

    def test_single_scan_sequence(self):
        """Verify the correct call sequence on instruments."""
        tsl = _make_mock_tsl()
        mpm = _make_mock_mpm()
        scanner = Scanner(tsl, mpm)
        scanner.configure(
            start_wl=1500.0, stop_wl=1500.004, step=0.001,
            speed=20.0, power=5.0
        )
        scanner.run_single_scan(mpm_range=1, plot=False)

        # Verify TSL sequence
        tsl.set_scan_start_mode.assert_called_with("WAITING_FOR_TRIGGER")
        tsl.start_sweep.assert_called_once()
        tsl.soft_trigger.assert_called_once()

        # Verify MPM sequence
        mpm.set_measurement_mode.assert_called()
        mpm.set_trigger_input.assert_called_with("EXTERNAL")
        mpm.set_range.assert_called_with(1)
        mpm.start_logging.assert_called_once()
        mpm.stop_logging.assert_called_once()
        mpm.get_channel_logging_data.assert_called_once()


class TestScannerMultiRange:
    def test_multi_range_runs_multiple_scans(self):
        tsl = _make_mock_tsl()
        mpm = _make_mock_mpm()
        scanner = Scanner(tsl, mpm)
        scanner.configure(
            start_wl=1500.0, stop_wl=1500.004, step=0.001,
            speed=20.0, power=5.0, ranges=[1, 3]
        )
        results = scanner.run_multi_range_scan(ranges=[1, 3], plot=False)
        assert len(results) == 2
        assert results[0].mpm_range == 1
        assert results[1].mpm_range == 3

    def test_multi_range_merge_called(self):
        tsl = _make_mock_tsl()
        mpm = _make_mock_mpm()
        scanner = Scanner(tsl, mpm)
        scanner.configure(
            start_wl=1500.0, stop_wl=1500.004, step=0.001,
            speed=20.0, power=5.0, ranges=[1, 3]
        )
        merged = scanner.run_multi_range_scan_merged(ranges=[1, 3], plot=False)
        assert isinstance(merged, ScanResult)
        assert merged.mpm_range == 0


class TestScannerILMeasurement:
    def test_run_il_measurement(self):
        tsl = _make_mock_tsl()
        mpm = _make_mock_mpm()
        scanner = Scanner(tsl, mpm)
        scanner.configure(
            start_wl=1500.0, stop_wl=1500.004, step=0.001,
            speed=20.0, power=5.0
        )
        result = scanner.run_il_measurement(ranges=[1], plot=False)
        assert isinstance(result, ILMeasurement)
        assert isinstance(result.reference, ScanResult)
        assert isinstance(result.measurement, ScanResult)
        assert len(result.il) == len(result.wavelengths)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_scanner.py -v`
Expected: FAIL — `ImportError` (Scanner, ILMeasurement not defined in scanner.py)

- [ ] **Step 3: Add Scanner class to scanner.py**

Append to `santecpro/scanner.py`:

```python
import time
import logging

logger = logging.getLogger(__name__)

# Polling interval for scan status checks (seconds)
_POLL_INTERVAL = 0.2


class Scanner:
    """Coordinates TSL sweep and MPM data acquisition.

    Usage:
        scanner = Scanner(tsl, mpm)
        scanner.configure(start_wl=1500, stop_wl=1630, step=0.001, speed=20, power=5)
        result = scanner.run_single_scan()
    """

    def __init__(self, tsl: TSLInstrument, mpm: MPMInstrument):
        self._tsl = tsl
        self._mpm = mpm
        self._config: dict = {}

    def configure(
        self,
        start_wl: float,
        stop_wl: float,
        step: float,
        speed: float,
        power: float,
        sweep_mode: str = "CONTINUOUS_ONE_WAY",
        ranges: list[int] | None = None,
        mpm_channel: int = 1,
        mpm_module: int = 1,
    ) -> None:
        """Configure all scan parameters on both instruments."""
        self._config = {
            "start_wl": start_wl,
            "stop_wl": stop_wl,
            "step": step,
            "speed": speed,
            "power": power,
            "sweep_mode": sweep_mode,
            "ranges": ranges or [1],
            "mpm_channel": mpm_channel,
            "mpm_module": mpm_module,
        }

        # Configure TSL
        self._tsl.set_power(power)
        self._tsl.set_sweep_mode(sweep_mode)
        self._tsl.configure_sweep(start_wl, stop_wl, step, speed)
        self._tsl.set_trigger_output("STEP")

        # Configure MPM (range set per-scan in run_single_scan)
        self._mpm.set_unit("dBm")
        self._mpm.set_range_mode("MANUAL")

        # Calculate expected data points
        self._data_points = int(round((stop_wl - start_wl) / step)) + 1
        self._mpm.set_logging_data_points(self._data_points)

        logger.info(
            "Configured scan: %s-%s nm, step=%s nm, speed=%s nm/s, power=%s dBm",
            start_wl, stop_wl, step, speed, power,
        )

    def run_single_scan(
        self,
        mpm_range: int = 1,
        plot: bool = True,
        save_csv: str | None = None,
    ) -> ScanResult:
        """Execute a single-range scan."""
        cfg = self._config
        ch = cfg["mpm_channel"]
        mod = cfg["mpm_module"]

        # Configure MPM for this range
        self._mpm.set_range(mpm_range)
        self._mpm.set_measurement_mode("SWEEP1")
        self._mpm.set_trigger_input("EXTERNAL")

        # Set TSL to wait for trigger before starting
        self._tsl.set_scan_start_mode("WAITING_FOR_TRIGGER")

        # Start MPM logging
        self._mpm.start_logging()

        # Start TSL sweep (enters STANDING_BY_TRIGGER)
        self._tsl.start_sweep()

        # Fire software trigger to begin actual sweep
        self._tsl.soft_trigger()

        # Poll MPM logging status until completed
        self._poll_mpm_logging()

        # Stop logging and sweep
        self._mpm.stop_logging()
        self._tsl.stop_sweep()

        # Retrieve data
        powers = np.array(
            self._mpm.get_channel_logging_data(module=mod, channel=ch)
        )
        monitor = np.array(
            self._tsl.get_power_monitor_data()
        )

        # Generate wavelength array
        wavelengths = np.linspace(cfg["start_wl"], cfg["stop_wl"], len(powers))

        result = ScanResult(
            wavelengths=wavelengths,
            powers=powers,
            monitor_powers=monitor,
            scan_params={
                **cfg,
                "mpm_range": mpm_range,
                "data_points": len(powers),
            },
            timestamp=datetime.now().isoformat(),
            mpm_range=mpm_range,
        )

        # Optional plot
        if plot:
            from santecpro.plotter import plot_scan_result
            plot_scan_result(result)

        # Optional CSV
        if save_csv:
            from santecpro.exporter import save_raw_csv
            save_raw_csv(result, self._tsl.idn, self._mpm.idn, save_csv)

        return result

    def run_multi_range_scan(
        self,
        ranges: list[int] | None = None,
        plot: bool = True,
        save_raw_csv: str | None = None,
    ) -> list[ScanResult]:
        """Execute multi-range scan (one sweep per range)."""
        ranges = ranges or self._config["ranges"]
        results = []
        for r in ranges:
            logger.info("Running scan with MPM range %d", r)
            result = self.run_single_scan(mpm_range=r, plot=False)
            results.append(result)
        return results

    def run_multi_range_scan_merged(
        self,
        ranges: list[int] | None = None,
        plot: bool = True,
        save_raw_csv: str | None = None,
    ) -> ScanResult:
        """Execute multi-range scan and merge results."""
        results = self.run_multi_range_scan(ranges=ranges, plot=False)
        merged = merge_multi_range(results)

        if plot:
            from santecpro.plotter import plot_scan_result
            plot_scan_result(merged)

        if save_raw_csv:
            from santecpro.exporter import save_raw_csv
            save_raw_csv(merged, self._tsl.idn, self._mpm.idn, save_raw_csv)

        return merged

    def run_reference_scan(self, mpm_range: int | None = None) -> ScanResult:
        """Execute reference scan. Auto-selects optimal range if not specified."""
        if mpm_range is None:
            power = self._mpm.get_power(self._config["mpm_channel"])
            mpm_range = self._mpm.select_optimal_range(power)
        return self.run_single_scan(mpm_range=mpm_range, plot=False)

    def run_il_measurement(
        self,
        ranges: list[int] | None = None,
        plot: bool = True,
        save_raw_csv: str | None = None,
        save_loss_csv: str | None = None,
    ) -> ILMeasurement:
        """Full IL measurement: reference + multi-range DUT + IL calculation."""
        # Reference scan
        reference = self.run_reference_scan()

        # DUT scan (multi-range)
        measurement = self.run_multi_range_scan_merged(
            ranges=ranges, plot=False, save_raw_csv=None
        )

        # Calculate IL
        il = calculate_il(reference, measurement)

        result = ILMeasurement(
            reference=reference,
            measurement=measurement,
            il=il,
            wavelengths=measurement.wavelengths,
        )

        if plot:
            from santecpro.plotter import plot_il_result
            plot_il_result(result)

        if save_raw_csv:
            from santecpro.exporter import save_raw_csv
            save_raw_csv(measurement, self._tsl.idn, self._mpm.idn, save_raw_csv)

        if save_loss_csv:
            from santecpro.exporter import save_loss_csv
            save_loss_csv(result, self._tsl.idn, self._mpm.idn, save_loss_csv)

        return result

    def _poll_mpm_logging(self, timeout: float = 300.0) -> None:
        """Poll MPM logging status until COMPLETED or timeout."""
        start = time.time()
        while time.time() - start < timeout:
            status, count = self._mpm.get_logging_status()
            if status == 1:  # COMPLETED
                logger.info("MPM logging completed, %d points", count)
                return
            time.sleep(_POLL_INTERVAL)
        raise TimeoutError(f"MPM logging did not complete within {timeout}s")


# Fix circular import: these are used by Scanner but defined in instruments/
from santecpro.instruments.tsl import TSLInstrument
from santecpro.instruments.mpm import MPMInstrument
```

Important: move the `import time` and `import logging` to the top of `scanner.py`. The full file should have these imports at the top:

```python
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from santecpro.instruments.mpm import MPM_RANGES
```

And remove the duplicate imports at the bottom. The `TSLInstrument` / `MPMInstrument` imports for type hints should use `TYPE_CHECKING`:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from santecpro.instruments.tsl import TSLInstrument
    from santecpro.instruments.mpm import MPMInstrument
```

And in the `Scanner.__init__` signature, use string annotations:
```python
def __init__(self, tsl: "TSLInstrument", mpm: "MPMInstrument"):
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_scanner.py -v`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add santecpro/scanner.py tests/test_scanner.py
git commit -m "feat: add Scanner coordinator with multi-range and IL measurement"
```

---

### Task 8: CSV Exporter

**Files:**
- Create: `santecpro/exporter.py`
- Create: `tests/test_exporter.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_exporter.py
"""Tests for santecpro.exporter."""

import csv
import os
import tempfile
import numpy as np
import pytest
from santecpro.exporter import save_raw_csv, save_loss_csv
from santecpro.scanner import ScanResult, ILMeasurement


def _make_scan_result():
    return ScanResult(
        wavelengths=np.array([1500.0, 1500.001, 1500.002]),
        powers=np.array([-33.268, -33.280, -33.275]),
        monitor_powers=np.array([7.58, 7.59, 7.60]),
        scan_params={
            "start_wl": 1500.0,
            "stop_wl": 1630.0,
            "step": 0.001,
            "speed": 20.0,
            "power": 0.0,
        },
        timestamp="2026-04-13T10:30:00",
        mpm_range=1,
    )


class TestSaveRawCsv:
    def test_creates_file(self):
        scan = _make_scan_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_raw.csv")
            save_raw_csv(scan, "SANTEC,TSL-550,12345,1.00", "SANTEC,MPM-210,67890,1.16", path)
            assert os.path.exists(path)

    def test_header_contains_metadata(self):
        scan = _make_scan_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_raw.csv")
            save_raw_csv(scan, "SANTEC,TSL-550,12345,1.00", "SANTEC,MPM-210,67890,1.16", path)
            with open(path, "r") as f:
                lines = f.readlines()
            # Line 2: Software info
            assert "santecpro" in lines[1]
            # Line 3: TSL info
            assert "TSL-550" in lines[2]
            # Line 4: MPM info
            assert "MPM-210" in lines[3]
            # Line 6: Start wavelength
            assert "Start" in lines[6]
            assert "1500" in lines[6]

    def test_data_rows_present(self):
        scan = _make_scan_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_raw.csv")
            save_raw_csv(scan, "SANTEC,TSL-550,12345,1.00", "SANTEC,MPM-210,67890,1.16", path)
            with open(path, "r") as f:
                lines = f.readlines()
            # Find data header
            data_start = None
            for i, line in enumerate(lines):
                if "Wavelength(nm)" in line:
                    data_start = i + 1
                    break
            assert data_start is not None
            assert data_start < len(lines)
            # First data row
            parts = lines[data_start].strip().split(",")
            assert float(parts[0]) == pytest.approx(1500.0)
            assert float(parts[1]) == pytest.approx(7.58)
            assert float(parts[2]) == pytest.approx(-33.268)


class TestSaveLossCsv:
    def test_creates_file(self):
        scan = _make_scan_result()
        il_meas = ILMeasurement(
            reference=scan,
            measurement=scan,
            il=np.array([0.0, 0.1, 0.2]),
            wavelengths=scan.wavelengths,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_loss.csv")
            save_loss_csv(il_meas, "SANTEC,TSL-550,12345,1.00", "SANTEC,MPM-210,67890,1.16", path)
            assert os.path.exists(path)

    def test_data_contains_il(self):
        scan = _make_scan_result()
        il_meas = ILMeasurement(
            reference=scan,
            measurement=scan,
            il=np.array([0.0, 0.1, 0.2]),
            wavelengths=scan.wavelengths,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_loss.csv")
            save_loss_csv(il_meas, "SANTEC,TSL-550,12345,1.00", "SANTEC,MPM-210,67890,1.16", path)
            with open(path, "r") as f:
                lines = f.readlines()
            data_start = None
            for i, line in enumerate(lines):
                if "Wavelength(nm)" in line:
                    data_start = i + 1
                    break
            assert data_start is not None
            parts = lines[data_start].strip().split(",")
            assert float(parts[0]) == pytest.approx(1500.0)
            assert float(parts[1]) == pytest.approx(0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_exporter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'santecpro.exporter'`

- [ ] **Step 3: Write the implementation**

```python
# santecpro/exporter.py
"""CSV export for raw and loss scan data (Santec STS compatible format)."""

from __future__ import annotations

import csv
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from santecpro.scanner import ScanResult, ILMeasurement


def _parse_idn(idn: str) -> dict:
    """Parse a '*IDN?' response into vendor, model, serial, firmware."""
    parts = idn.split(",")
    return {
        "vendor": parts[0] if len(parts) > 0 else "",
        "model": parts[1] if len(parts) > 1 else "",
        "serial": parts[2] if len(parts) > 2 else "",
        "firmware": parts[3] if len(parts) > 3 else "",
    }


def _write_header(
    writer: csv.writer,
    tsl_idn: str,
    mpm_idn: str,
    params: dict,
    timestamp: str,
) -> None:
    """Write the 14-line metadata header common to raw and loss CSV."""
    now = datetime.fromisoformat(timestamp) if "T" in timestamp else datetime.now()
    date_str = now.strftime("%Y/%m/%d")
    time_str = now.strftime("%H:%M:%S")

    tsl = _parse_idn(tsl_idn)
    mpm = _parse_idn(mpm_idn)

    writer.writerow([date_str, time_str, "", ""])
    writer.writerow(["Software", "santecpro", "Ver.1.0.0", ""])
    writer.writerow(["TSL", tsl["vendor"], tsl["model"], tsl["serial"], tsl["firmware"], "", "", ""])
    writer.writerow(["PowerMeter", mpm["vendor"], mpm["model"], mpm["serial"], mpm["firmware"], "", "", ""])
    writer.writerow(["", "Module1", "MPM-211", "", ""])
    writer.writerow(["", "", "", "", ""])
    writer.writerow(["Start", f"{params.get('start_wl', 0):.6f}", "nm", "", ""])
    writer.writerow(["Stop", f"{params.get('stop_wl', 0):.6f}", "nm", "", ""])
    writer.writerow(["Step", f"{params.get('step', 0):.6f}", "nm", "", ""])
    writer.writerow(["Speed", f"{params.get('speed', 0):.6f}", "nm/s", "", ""])
    writer.writerow(["Source power", f"{params.get('power', 0):.6f}", "dBm", "", ""])
    writer.writerow(["Averaging Time", "", "s", "", ""])
    writer.writerow(["Power meter range", "", "dBm", "", ""])
    writer.writerow(["Sweep mode", params.get("sweep_mode", "CONTINUOUS_ONE_WAY"), "", "", ""])


def save_raw_csv(
    scan: "ScanResult",
    tsl_idn: str,
    mpm_idn: str,
    filepath: str,
) -> None:
    """Save raw scan data (wavelength + monitor + MPM power) as CSV."""
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        _write_header(writer, tsl_idn, mpm_idn, scan.scan_params, scan.timestamp)
        writer.writerow(["Wavelength(nm)", "Monitor(dBm)", "M1-Ch1(dBm)", "", ""])
        for wl, mon, pwr in zip(scan.wavelengths, scan.monitor_powers, scan.powers):
            writer.writerow([f"{wl:.8f}", f"{mon:.5f}", f"{pwr:.5f}", "", ""])


def save_loss_csv(
    il_measurement: "ILMeasurement",
    tsl_idn: str,
    mpm_idn: str,
    filepath: str,
) -> None:
    """Save IL (insertion loss) data as CSV."""
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        _write_header(
            writer, tsl_idn, mpm_idn,
            il_measurement.measurement.scan_params,
            il_measurement.measurement.timestamp,
        )
        writer.writerow(["Wavelength(nm)", "IL_M1_CH1", "", "", ""])
        for wl, il in zip(il_measurement.wavelengths, il_measurement.il):
            writer.writerow([f"{wl:.8f}", f"{il:.8f}", "", "", ""])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_exporter.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add santecpro/exporter.py tests/test_exporter.py
git commit -m "feat: add CSV exporter with raw and loss formats"
```

---

### Task 9: Real-Time Plotter

**Files:**
- Create: `santecpro/plotter.py`
- Create: `tests/test_plotter.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_plotter.py
"""Tests for santecpro.plotter."""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from santecpro.plotter import plot_scan_result, plot_il_result
from santecpro.scanner import ScanResult, ILMeasurement


def _make_scan_result():
    return ScanResult(
        wavelengths=np.array([1500.0, 1510.0, 1520.0]),
        powers=np.array([-10.0, -15.0, -20.0]),
        monitor_powers=np.array([7.5, 7.6, 7.7]),
        scan_params={},
        timestamp="2026-04-13T10:30:00",
        mpm_range=1,
    )


class TestPlotScanResult:
    @patch("santecpro.plotter.plt")
    def test_plot_creates_figure(self, mock_plt):
        scan = _make_scan_result()
        plot_scan_result(scan)
        mock_plt.figure.assert_called_once()
        mock_plt.plot.assert_called_once()
        mock_plt.show.assert_called_once()

    @patch("santecpro.plotter.plt")
    def test_plot_sets_labels(self, mock_plt):
        scan = _make_scan_result()
        plot_scan_result(scan)
        mock_plt.xlabel.assert_called_once()
        mock_plt.ylabel.assert_called_once()
        mock_plt.title.assert_called_once()


class TestPlotILResult:
    @patch("santecpro.plotter.plt")
    def test_plot_il_creates_figure(self, mock_plt):
        scan = _make_scan_result()
        il_meas = ILMeasurement(
            reference=scan,
            measurement=scan,
            il=np.array([0.0, 5.0, 10.0]),
            wavelengths=scan.wavelengths,
        )
        plot_il_result(il_meas)
        mock_plt.figure.assert_called_once()
        mock_plt.plot.assert_called_once()
        mock_plt.show.assert_called_once()

    @patch("santecpro.plotter.plt")
    def test_plot_il_title(self, mock_plt):
        scan = _make_scan_result()
        il_meas = ILMeasurement(
            reference=scan,
            measurement=scan,
            il=np.array([0.0, 5.0, 10.0]),
            wavelengths=scan.wavelengths,
        )
        plot_il_result(il_meas)
        mock_plt.title.assert_called_once()
        title_arg = mock_plt.title.call_args[0][0]
        assert "IL" in title_arg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_plotter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'santecpro.plotter'`

- [ ] **Step 3: Write the implementation**

```python
# santecpro/plotter.py
"""Real-time plotting for wavelength scan results."""

from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from santecpro.scanner import ScanResult, ILMeasurement


def plot_scan_result(scan: "ScanResult") -> None:
    """Plot wavelength vs power for a scan result."""
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(scan.wavelengths, scan.powers, linewidth=0.8)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Power (dBm)")
    ax.set_title(
        f"Wavelength Scan — {scan.wavelengths[0]:.1f}–{scan.wavelengths[-1]:.1f} nm, "
        f"Range {scan.mpm_range}, {len(scan.powers)} points"
    )
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


def plot_il_result(il_measurement: "ILMeasurement") -> None:
    """Plot insertion loss vs wavelength."""
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(il_measurement.wavelengths, il_measurement.il, linewidth=0.8)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Insertion Loss (dB)")
    ax.set_title(
        f"IL Measurement — {il_measurement.wavelengths[0]:.1f}–"
        f"{il_measurement.wavelengths[-1]:.1f} nm"
    )
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_plotter.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add santecpro/plotter.py tests/test_plotter.py
git commit -m "feat: add real-time plotter for scan and IL results"
```

---

### Task 10: Usage Example and Package Finalization

**Files:**
- Create: `examples/basic_scan.py`
- Modify: `santecpro/__init__.py`

- [ ] **Step 1: Update santecpro/__init__.py with public API**

```python
# santecpro/__init__.py
"""Santecpro — Cross-platform Python driver for Santec TSL-550 and MPM-210."""

__version__ = "1.0.0"

from santecpro.instruments.tsl import TSLInstrument
from santecpro.instruments.mpm import MPMInstrument
from santecpro.scanner import Scanner, ScanResult, ILMeasurement

__all__ = [
    "TSLInstrument",
    "MPMInstrument",
    "Scanner",
    "ScanResult",
    "ILMeasurement",
]
```

- [ ] **Step 2: Create examples/basic_scan.py**

```python
#!/usr/bin/env python3
"""Basic scan example for Santec TSL-550 + MPM-210.

Usage:
    python examples/basic_scan.py

Prerequisites:
    - NI-VISA runtime installed
    - TSL-550 connected via GPIB (default address: 10)
    - MPM-210 connected via GPIB (default address: 17)
"""

import pyvisa
from santecpro import TSLInstrument, MPMInstrument, Scanner


def main():
    # Initialize VISA resource manager
    rm = pyvisa.ResourceManager()

    # Print available resources
    print("Available VISA resources:")
    for r in rm.list_resources():
        print(f"  {r}")

    # Connect to instruments
    print("\nConnecting to TSL-550...")
    tsl = TSLInstrument(rm)
    tsl.connect("GPIB0::10::INSTR")
    print(f"  TSL IDN: {tsl.idn}")

    print("Connecting to MPM-210...")
    mpm = MPMInstrument(rm)
    mpm.connect("GPIB0::17::INSTR")
    print(f"  MPM IDN: {mpm.idn}")

    # Turn on laser
    tsl.laser_on()
    tsl.shutter_open()

    # Configure and run a basic scan
    scanner = Scanner(tsl, mpm)
    scanner.configure(
        start_wl=1550.0,
        stop_wl=1560.0,
        step=0.01,
        speed=20.0,
        power=0.0,
        sweep_mode="CONTINUOUS_ONE_WAY",
        ranges=[1],
    )

    print("\nStarting scan...")
    result = scanner.run_single_scan(
        mpm_range=1,
        plot=True,
        save_csv="scan_result_raw.csv",
    )
    print(f"Scan complete: {len(result.wavelengths)} data points")
    print(f"Wavelength range: {result.wavelengths[0]:.3f} – {result.wavelengths[-1]:.3f} nm")
    print(f"Power range: {result.powers.min():.2f} – {result.powers.max():.2f} dBm")

    # Cleanup
    tsl.shutter_close()
    tsl.laser_off()
    tsl.disconnect()
    mpm.disconnect()
    rm.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
git add santecpro/__init__.py examples/basic_scan.py
git commit -m "feat: add usage example and finalize package public API"
```

---

### Task 11: Run All Tests

- [ ] **Step 1: Run the full test suite**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/ -v`
Expected: All tests pass (exceptions: 5, base: 11, tsl: 24, mpm: 20, scanner: ~15, exporter: 4, plotter: 4)

- [ ] **Step 2: Fix any failures**

If any test fails, read the error output, fix the code, and re-run.

- [ ] **Step 3: Commit if fixes were needed**

```bash
git add -A
git commit -m "fix: resolve test failures from full suite run"
```

---

### Task 12: SCPI Debug/Trace Mode

The spec requires a SCPI command trace mode for debugging. This is added to BaseInstrument.

**Files:**
- Modify: `santecpro/instruments/base.py`
- Modify: `tests/test_base.py`

- [ ] **Step 1: Write the test**

Append to `tests/test_base.py`:

```python
import logging
from io import StringIO


class TestScpiTrace:
    def test_trace_logs_queries(self, mock_resource_manager, mock_resource, caplog):
        mock_resource.query.return_value = "5.000"
        inst = BaseInstrument(mock_resource_manager, trace=True)
        inst.connect("GPIB0::10::INSTR")
        with caplog.at_level(logging.DEBUG, logger="santecpro.trace"):
            inst.query("POW:LEV?")
        assert "POW:LEV?" in caplog.text
        assert "5.000" in caplog.text

    def test_trace_logs_writes(self, mock_resource_manager, mock_resource, caplog):
        inst = BaseInstrument(mock_resource_manager, trace=True)
        inst.connect("GPIB0::10::INSTR")
        with caplog.at_level(logging.DEBUG, logger="santecpro.trace"):
            inst.write("POW:LEV 5")
        assert "POW:LEV 5" in caplog.text

    def test_trace_disabled_by_default(self, mock_resource_manager, mock_resource, caplog):
        mock_resource.query.return_value = "5.000"
        inst = BaseInstrument(mock_resource_manager)
        inst.connect("GPIB0::10::INSTR")
        with caplog.at_level(logging.DEBUG, logger="santecpro.trace"):
            inst.query("POW:LEV?")
        assert "POW:LEV?" not in caplog.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_base.py::TestScpiTrace -v`
Expected: FAIL — `BaseInstrument.__init__() got an unexpected keyword argument 'trace'`

- [ ] **Step 3: Modify base.py to add trace support**

Update `BaseInstrument.__init__` in `santecpro/instruments/base.py`:

```python
import logging

_trace_logger = logging.getLogger("santecpro.trace")


class BaseInstrument:
    def __init__(self, resource_manager, trace: bool = False):
        self._rm = resource_manager
        self._resource = None
        self._trace = trace
```

Update `query` and `write` methods:

```python
    def query(self, command: str) -> str:
        self._require_connected()
        if self._trace:
            _trace_logger.debug("Q: %s", command)
        response = self._resource.query(command)
        if self._trace:
            _trace_logger.debug("R: %s", response)
        return response

    def write(self, command: str) -> None:
        self._require_connected()
        if self._trace:
            _trace_logger.debug("W: %s", command)
        self._resource.write(command)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/x/Library/CloudStorage/OneDrive-Personal/Project/python/santecpro && python -m pytest tests/test_base.py -v`
Expected: All base tests pass (existing + 3 new)

- [ ] **Step 5: Commit**

```bash
git add santecpro/instruments/base.py tests/test_base.py
git commit -m "feat: add SCPI command trace/debug mode to BaseInstrument"
```

---

## Self-Review Checklist

**1. Spec Coverage:**
- [x] TSL-550 control (all SCPI commands) → Task 4
- [x] MPM-210 control (all SCPI commands + ranges) → Task 5
- [x] Wavelength scanning with configurable params → Task 7
- [x] Forward and bidirectional sweep modes → Task 7 (sweep_mode param)
- [x] Single-range scanning → Task 7 (`run_single_scan`)
- [x] Multi-range scanning with merge → Task 7 (`run_multi_range_scan_merged`)
- [x] Reference scan + IL calculation → Task 7 (`run_il_measurement`)
- [x] Real-time plotting → Task 9
- [x] CSV export raw format → Task 8
- [x] CSV export loss format → Task 8
- [x] Error handling (custom exceptions) → Task 2
- [x] SCPI trace/debug mode → Task 12

**2. Placeholder scan:** No TBD, TODO, or "implement later" found.

**3. Type consistency:** All method names and signatures match across tasks. `ScanResult.mpm_range` is `int`, `merge_multi_range` returns `ScanResult` with `mpm_range=0`, `calculate_il` takes two `ScanResult` and returns `np.ndarray`.
