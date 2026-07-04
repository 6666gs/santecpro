# Santec Spectrum Scanner - Design Spec

**Date:** 2026-04-13
**Status:** Approved
**Target:** Cross-platform (macOS primary) pure-Python rewrite of Santec swept test system

## Background

Santec provides two Python libraries (PySantec, Python-IL-STS) for controlling TSL tunable lasers and MPM power meters. Both depend on Santec's .NET Framework DLLs via `pythonnet`, making them Windows-only. This project rewrites the core functionality in pure Python using PyVISA for cross-platform support, targeting macOS.

## Requirements

- **Devices:** TSL-550 (tunable laser) + MPM-210 (multi-channel power meter)
- **Connection:** GPIB via NI-VISA
- **Features:**
  - Wavelength scanning with configurable step, speed, power
  - Forward (one-way) and bidirectional (two-way) continuous sweep
  - Single-range and multi-range scanning with automatic data merging
  - Reference scan + DUT measurement for Insertion Loss (IL) calculation
  - Real-time plotting during scan
  - CSV export in raw and loss formats (compatible with Santec STS software)
- **No DAQ support needed**
- **No .NET dependency**

## Architecture

```
santecpro/
├── santecpro/
│   ├── __init__.py
│   ├── instruments/
│   │   ├── __init__.py
│   │   ├── base.py          # BaseInstrument: pyvisa wrapper
│   │   ├── tsl.py           # TSLInstrument: TSL-550 laser control
│   │   └── mpm.py           # MPMInstrument: MPM-210 power meter control
│   ├── scanner.py           # Scanner: scan coordination (TSL + MPM sync)
│   ├── plotter.py           # Real-time wavelength-power plotting
│   └── exporter.py          # CSV export (raw + loss formats)
├── examples/
│   └── basic_scan.py        # Usage example
├── pyproject.toml
└── requirements.txt
```

### Dependencies

- `pyvisa` >= 1.14 — VISA instrument communication (GPIB/TCP-IP/USB)
- `numpy` >= 2.0 — Array operations, interpolation
- `matplotlib` >= 3.9 — Real-time plotting

## Module Details

### 1. `base.py` — BaseInstrument

Wraps a `pyvisa.ResourceManager` resource. All instrument classes inherit from this.

**Methods:**
- `connect(resource_string: str)` — Open VISA resource, configure terminator
- `disconnect()` — Close VISA resource
- `query(command: str) -> str` — Send SCPI query, return response string
- `write(command: str) -> int` — Send SCPI command, return status
- `read() -> str` — Read response from instrument
- `idn -> str` — Property: send `*IDN?`, return identification string
- `timeout` — Property: get/set VISA timeout (ms)

### 2. `tsl.py` — TSLInstrument (extends BaseInstrument)

Controls TSL-550 tunable laser via SCPI commands.

**SCPI Command Mapping:**

| Method | SCPI Command | Description |
|--------|-------------|-------------|
| `laser_on()` | `LD:STAT ON` | Enable laser diode |
| `laser_off()` | `LD:STAT OFF` | Disable laser diode |
| `get_laser_status() -> str` | `LD:STAT?` | Query laser diode status |
| `shutter_open()` | `SHUT ON` | Open shutter |
| `shutter_close()` | `SHUT OFF` | Close shutter |
| `get_shutter_status() -> str` | `SHUT?` | Query shutter status |
| `set_power(power_dbm: float)` | `POW:LEV {value}` | Set output power (dBm) |
| `get_power() -> float` | `POW:LEV?` | Read current power setting |
| `set_wavelength(wl_nm: float)` | `WAV {value}` | Set wavelength (nm) |
| `get_wavelength() -> float` | `WAV?` | Read current wavelength |
| `set_sweep_mode(mode: str)` | `SWEEP:MODE {mode}` | CONT_ONEWAY, CONT_TWOWAY, STEP_ONEWAY, STEP_TWOWAY |
| `set_sweep_speed(speed: float)` | `SWEEP:SPED {value}` | Set sweep speed (nm/s) |
| `get_sweep_speed() -> float` | `SWEEP:SPED?` | Read sweep speed |
| `set_sweep_start(wl: float)` | `SWEEP:STAR:WAV {value}` | Set sweep start wavelength (nm) |
| `set_sweep_stop(wl: float)` | `SWEEP:STOP:WAV {value}` | Set sweep stop wavelength (nm) |
| `set_sweep_step(step: float)` | `SWEEP:STEP {value}` | Set sweep step (nm) |
| `set_trigger_output(mode: str)` | `TRIG:OUTP {mode}` | NONE, STOP, START, STEP |
| `set_scan_start_mode(mode: str)` | `SWEEP:STAR:MOD {mode}` | NORMAL, WAITING_FOR_TRIGGER |
| `start_sweep()` | `SWEEP:STAT START` | Start sweep |
| `stop_sweep()` | `SWEEP:STAT STOP` | Stop sweep |
| `pause_sweep()` | `SWEEP:STAT PAUSE` | Pause sweep |
| `restart_sweep()` | `SWEEP:STAT REST` | Restart paused sweep |
| `get_sweep_status() -> str` | `SWEEP:STAT?` | Query sweep status |
| `soft_trigger()` | `TRIG:SOFT` | Issue software trigger |
| `status_clear()` | `*CLS` | Clear status |
| `device_reset()` | `*RST` | Reset device |
| `get_logging_data_points() -> int` | `:READ:POIN?` | Get number of logged data points |
| `get_power_monitor_data() -> list` | `:READ:POW?` | Read TSL power monitor log data |

**Initialization on connect:**
1. Set terminator to CR
2. Send `*CLS` (clear status)
3. Send `*RST` (reset)

### 3. `mpm.py` — MPMInstrument (extends BaseInstrument)

Controls MPM-210 power meter via SCPI commands.

**MPM Dynamic Ranges:**

| Range | Dynamic Range |
|-------|--------------|
| 1 | -30 ~ +10 dBm |
| 2 | -40 ~ 0 dBm |
| 3 | -50 ~ -10 dBm |
| 4 | -60 ~ -20 dBm |
| 5 | -80 ~ -30 dBm |

**SCPI Command Mapping:**

| Method | SCPI Command | Description |
|--------|-------------|-------------|
| `set_wavelength(wl_nm: float)` | `WAV {value}` | Set working wavelength |
| `set_range(range_val: int)` | `RANG {value}` | Set power range (1-5) |
| `set_range_mode(mode: str)` | `RANG:MOD {mode}` | MANUAL / AUTO |
| `set_range_per_channel(ch: int, range_val: int)` | `RANG:CH{ch} {value}` | Set range per channel |
| `set_averaging_time(time: float)` | `AVG {value}` | Set averaging time |
| `get_averaging_time() -> float` | `AVG?` | Read averaging time |
| `set_unit(unit: str)` | `POW:UNIT {unit}` | dBm / mW |
| `get_power(channel: int) -> float` | `READ:POW:CH{ch}?` | Read channel power |
| `set_logging_params(start, stop, step, speed, ...)` | `LOGG:PARA ...` | Configure logging parameters |
| `set_logging_data_points(n: int)` | `LOGG:POIN {n}` | Set expected data points |
| `start_logging()` | `LOGG:STAT START` | Start logging |
| `stop_logging()` | `LOGG:STAT STOP` | Stop logging |
| `get_logging_status() -> tuple[int, int]` | `LOGG:STAT?` | (status, count); -1=stopped, 0=logging, 1=completed |
| `get_channel_logging_data(module: int, channel: int) -> list` | `LOGG:CH{ch}:DATA?` | Retrieve logged power data |
| `get_module_logging_data(module: int) -> list` | `LOGG:MOD{mod}:DATA?` | Retrieve module data |
| `perform_zeroing()` | `ZERO` | Zero the power meter |
| `set_measurement_mode(mode: str)` | `MOD {mode}` | SWEEP1/SWEEP2/FREERUN |
| `set_trigger_input(mode: str)` | `TRIG:INP {mode}` | INTERNAL / EXTERNAL |

### 4. `scanner.py` — Scan Coordinator

Synchronizes TSL sweep and MPM data acquisition.

**Data Classes:**

```python
@dataclass
class ScanResult:
    wavelengths: np.ndarray     # nm
    powers: np.ndarray          # dBm (MPM measured)
    monitor_powers: np.ndarray  # dBm (TSL power monitor)
    scan_params: dict           # Full parameter record
    timestamp: str              # ISO format timestamp
    mpm_range: int              # Range used for this scan
```

**Scanner Class:**

```python
class Scanner:
    def __init__(self, tsl: TSLInstrument, mpm: MPMInstrument):
        """Initialize with connected instruments."""

    def configure(self,
                  start_wl: float,       # nm
                  stop_wl: float,        # nm
                  step: float,           # nm
                  speed: float,          # nm/s
                  power: float,          # dBm
                  sweep_mode: str = "CONTINUOUS_ONE_WAY",
                  ranges: list[int] = None,  # MPM ranges, default [1]
                  mpm_channel: int = 1):
        """Configure all scan parameters on both instruments."""

    def run_single_scan(self, mpm_range: int = 1,
                        plot: bool = True,
                        save_csv: str | None = None) -> ScanResult:
        """Execute a single-range scan."""

    def run_multi_range_scan(self, ranges: list[int] = None,
                             plot: bool = True,
                             save_raw_csv: str | None = None) -> list[ScanResult]:
        """Execute multi-range scan (one sweep per range)."""

    def merge_multi_range(self, scan_results: list[ScanResult]) -> ScanResult:
        """Merge multi-range data into a single wide-dynamic-range curve.
        For each wavelength point, select data from the range where the
        signal is within the valid measurement range."""

    def run_reference_scan(self,
                           mpm_range: int | None = None) -> ScanResult:
        """Execute reference scan (no DUT). Auto-selects optimal range."""

    def run_il_measurement(self,
                           ranges: list[int] = None,
                           plot: bool = True,
                           save_raw_csv: str | None = None,
                           save_loss_csv: str | None = None) -> ILMeasurement:
        """Full IL measurement: reference scan + multi-range DUT scan + IL calculation."""

    def calculate_il(self,
                     reference: ScanResult,
                     measurement: ScanResult) -> np.ndarray:
        """Calculate insertion loss: IL = P_ref - P_meas (linear interpolation
        to align wavelength grids if needed)."""
```

**Single-Range Scan Sequence:**

```
1. Configure TSL: sweep params, trigger output = STEP, scan start mode = WAITING_FOR_TRIGGER
2. Configure MPM: range mode, measurement mode, trigger input = EXTERNAL, logging params, data points
3. Set TSL scan start mode = WAITING_FOR_TRIGGER
4. Start MPM logging
5. Start TSL sweep → TSL enters STANDING_BY_TRIGGER
6. Send TSL soft trigger → sweep begins
7. Poll MPM logging status until COMPLETED
8. Stop TSL sweep
9. Retrieve MPM logging data
10. Generate wavelength array from (start, step, count)
11. Return ScanResult
```

**Multi-Range Scan Sequence:**

```
1. Configure TSL once (same sweep params for all ranges)
2. For each range in ranges:
   a. Set MPM range
   b. Execute single-range scan sequence (steps 3-9 above)
   c. Store ScanResult
3. Call merge_multi_range() to combine results
4. Return merged ScanResult
```

**Multi-Range Merge Algorithm:**

For each wavelength point:
1. Check which ranges have valid data at this wavelength
2. A range is valid when the measured power is within its dynamic range (e.g., range 1: -30 to +10 dBm)
3. If multiple ranges are valid, prefer the range with the highest signal-to-noise ratio (lowest range number that still captures the signal)
4. If no range is valid (gap), use NaN
5. Concatenate into a single continuous array

**IL Calculation:**

```
IL(λ) = P_reference(λ) - P_measurement(λ)
```

Where powers are in dBm, so IL is in dB. If wavelength grids differ between reference and measurement, use `numpy.interp` to align.

### 5. `plotter.py` — Real-Time Plotting

Uses matplotlib to display wavelength-power curves during scanning.

**Features:**
- Non-blocking plot updates using `matplotlib.pyplot.pause()`
- X-axis: wavelength (nm), Y-axis: power (dBm)
- Title shows scan progress (data points collected / total)
- Support for showing multiple range curves on the same plot
- IL plot mode: shows IL(dB) vs wavelength

### 6. `exporter.py` — CSV Export

Exports scan data in two formats compatible with Santec STS software.

**Raw CSV Format:**

```csv
2026/4/13,10:30:00,,,
Software,santecpro,Ver.1.0.0,,
TSL,SANTEC,TSL-550,<serial>,<firmware>,,,
PowerMeter,SANTEC,MPM-210,<serial>,<firmware>,,,
,Module1,MPM-211,<serial>,<module_id>
Start,1500.000000,nm,,
Stop,1630.000000,nm,,
Step,0.001000,nm,,
Speed,20.000000,nm/s,,
Source power,0.000000,dBm,,
Averaging Time,0.000050,s,,
Power meter range,,dBm,,
Sweep mode,CONTINUOUS_ONE_WAY,,,
Wavelength(nm),Monitor(dBm),M1-Ch1(dBm),,
1500.00000,7.58007,-33.26828,,
...
```

**Loss CSV Format:**

```csv
2026/4/13,10:30:00,,,
Software,santecpro,Ver.1.0.0,,
TSL,SANTEC,TSL-550,<serial>,<firmware>,,,
PowerMeter,SANTEC,MPM-210,<serial>,<firmware>,,,
,Module1,MPM-211,<serial>,<module_id>
Start,1500.000000,nm,,
Stop,1630.000000,nm,,
Step,0.001000,nm,,
Speed,20.000000,nm/s,,
Source power,0.000000,dBm,,
Averaging Time,0.000050,s,,
Power meter range,,dBm,,
Sweep mode,CONTINUOUS_ONE_WAY,,,
Wavelength(nm),IL_M1_CH1,,,
1500.00000000,0.25649587,,,
...
```

Header fields are populated from `ScanResult.scan_params` and instrument identification data.

## Error Handling

- All SCPI communication errors wrapped in custom `SantecError` exception
- Timeout handling for both TSL sweep status polling and MPM logging status polling
- Validation of scan parameters (wavelength range within spec, step > 0, etc.)
- Connection validation before scan execution

## Testing Strategy

- Unit tests for merge algorithm and IL calculation (pure numpy, no hardware needed)
- Mock-based tests for scanner sequence (mock pyvisa resources)
- Integration tests require actual hardware connection

## SCPI Command Verification

The SCPI commands listed in this spec are derived from reverse-engineering the DLL source code in PySantec and Python-IL-STS. Before implementation, the following must be verified against the official TSL-550 and MPM-210 programming manuals:

1. **MPM logging parameter commands** — The DLL uses `Set_Logging_Paremeter_for_STS` which may map to a compound SCPI sequence rather than a single `LOGG:PARA` command. The exact SCPI syntax for configuring MPM logging (start/stop wavelength, step, speed, TSL actual step) needs confirmation.
2. **MPM logging data retrieval** — `Get_Each_Channel_Logdata` and `Get_Each_Module_Loggdata` may use specific query formats that differ from `LOGG:CH{ch}:DATA?`.
3. **TSL power monitor data** — `Get_Logging_Data_Power_for_STS` retrieves the TSL's built-in power monitor log. The SCPI equivalent needs verification.
4. **Sweep modes** — The exact SCPI string values for sweep modes (CONT_ONEWAY, etc.) may differ from what the DLL sends.

**Mitigation:** The implementation should include a SCPI command debug/trace mode that logs all commands sent and responses received, making it easy to compare against the DLL behavior or adjust commands based on the instrument manual.

## Limitations

- GPIB requires NI-VISA runtime installed on macOS
- No DAQ/SPU support (not needed by user)
- No PDL (Polarization Dependent Loss) measurement support
