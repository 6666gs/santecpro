"""MPM-210 Multi-Channel Power Meter instrument driver.

Uses the Santec MPM-210 native command set (NOT standard SCPI).
Commands are plain keywords without colons (e.g. ``WMOD SWEEP1``,
``LEV 3``, ``READ? 0``).

Binary data returned by ``LOGG?`` follows IEEE 488.2 definite-length
block format with IEEE-754 single-precision floats (4 bytes each, LSB first).
"""

from __future__ import annotations

import struct

from santecpro.exceptions import InstrumentOperationError
from santecpro.instruments.base import BaseInstrument

# MPM-211 module dynamic ranges: range_number -> (min_dBm, max_dBm)
MPM_RANGES: dict[int, tuple[float, float]] = {
    1: (-30, 10),
    2: (-40, 0),
    3: (-50, -10),
    4: (-60, -20),
    5: (-80, -30),
}

# Measurement modes (WMOD parameter)
MEAS_MODE_CONST1 = "CONST1"  # Constant wavelength, manual range
MEAS_MODE_SWEEP1 = "SWEEP1"  # Sweep wavelength, manual range
MEAS_MODE_CONST2 = "CONST2"  # Constant wavelength, auto range
MEAS_MODE_SWEEP2 = "SWEEP2"  # Sweep wavelength, auto range
MEAS_MODE_FREERUN = "FREERUN"  # Constant wavelength, hardware trigger start


class MPMInstrument(BaseInstrument):
    """Driver for the Santec MPM-210 multi-channel power meter.

    Communicates over GPIB (LF terminator) or TCP/IP.
    """

    def connect(self, resource_string: str) -> None:
        """Connect to MPM via GPIB with LF terminator."""
        super().connect(resource_string, terminator="\n")
        assert self._resource is not None
        self._resource.timeout = 5000

    def connect_tcpip(self, ip_address: str, port: int = 5000) -> None:
        """Connect to MPM via TCP/IP (LAN).

        Args:
            ip_address: IP address of the MPM-210, e.g. "192.168.1.10"
            port: Port number, default 5000 (Santec default)
        """
        resource_string = f"TCPIP0::{ip_address}::{port}::SOCKET"
        super().connect(resource_string, terminator="\n")
        assert self._resource is not None
        self._resource.timeout = 10000

    # --- Wavelength ---
    # WAV — for CONST1/CONST2 mode

    def set_wavelength(self, wl_nm: float) -> None:
        self.write(f"WAV {wl_nm:.6f}")

    def get_wavelength(self) -> float:
        return float(self.query("WAV?"))

    # --- Range (LEV) control ---
    # LEV — sets TIA gain for CONST1/SWEEP1/FREERUN modes

    def set_range(self, range_val: int) -> None:
        """Set power range / TIA gain (1-5)."""
        self.write(f"LEV {range_val}")

    def get_range(self) -> int:
        """Query current range setting."""
        return int(self.query("LEV?"))

    def set_range_mode(self, mode: int) -> None:
        """Set auto range mode: 0=Manual, 1=Auto (AUTO command)."""
        self.write(f"AUTO {mode}")

    def get_range_mode(self) -> int:
        """Query auto range mode."""
        return int(self.query("AUTO?"))

    # --- Averaging ---

    def set_averaging_time(self, time_ms: float) -> None:
        """Set averaging time in ms (0.01–10000.00)."""
        self.write(f"AVG {time_ms:.2f}")

    def get_averaging_time(self) -> float:
        return float(self.query("AVG?"))

    # --- Unit ---

    def set_unit(self, unit: int) -> None:
        """Set power unit: 0=dBm (or dBmA), 1=mW (or mA)."""
        self.write(f"UNIT {unit}")

    def get_unit(self) -> int:
        return int(self.query("UNIT?"))

    # --- Power reading ---
    # READ? <module> — returns comma-separated values for all ports

    def get_power(self, module: int = 0) -> list[float]:
        """Read power from all ports of a module.

        Args:
            module: Module number (0-4), default 0.
        Returns:
            List of power values for ports 1-4.
        """
        raw = self.query(f"READ? {module}")
        return [float(v) for v in raw.split(",") if v.strip()]

    def get_power_channel(self, module: int, channel: int) -> float:
        """Read power from a specific module and channel.

        Args:
            module: Module number (0-4).
            channel: Port number (1-4).
        """
        values = self.get_power(module)
        return values[channel - 1]

    # --- Measurement mode ---

    def set_measurement_mode(self, mode: str) -> None:
        """Set measurement mode: CONST1, SWEEP1, CONST2, SWEEP2, FREERUN."""
        self.write(f"WMOD {mode}")

    def get_measurement_mode(self) -> str:
        return self.query("WMOD?")

    # --- Sweep wavelength configuration ---
    # WSET / SPE — for SWEEP1/SWEEP2 modes

    def set_sweep_wavelength(self, start: float, stop: float, step: float) -> None:
        """Set sweep wavelength range (WSET command).

        Data points = (stop - start) / step + 1 (auto-calculated).
        """
        self.write(f"WSET {start:.6f},{stop:.6f},{step:.6f}")

    def get_sweep_wavelength(self) -> tuple[float, float, float]:
        """Query sweep wavelength settings. Returns (start, stop, step)."""
        raw = self.query("WSET?")
        parts = raw.split(",")
        return float(parts[0]), float(parts[1]), float(parts[2])

    def set_sweep_speed(self, speed: float) -> None:
        """Set sweep speed in nm/s (SPE command)."""
        self.write(f"SPE {speed:.3f}")

    def get_sweep_speed(self) -> float:
        return float(self.query("SPE?"))

    # --- Trigger ---

    def set_trigger_input(self, mode: int) -> None:
        """Set trigger input: 0=Internal, 1=External."""
        self.write(f"TRIG {mode}")

    def get_trigger_input(self) -> int:
        return int(self.query("TRIG?"))

    # --- Logging / Measurement ---

    def set_logging_data_points(self, n: int) -> None:
        """Set measurement data points (LOGN command).

        For SWEEP modes, this is auto-calculated from WSET.
        For CONST1/CONST2/FREERUN, must be set manually.
        """
        self.write(f"LOGN {n}")

    def get_logging_data_points(self) -> int:
        """Query measurement data points."""
        return int(self.query("LOGN?"))

    def start_logging(self) -> None:
        """Start measurement (MEAS command)."""
        self.write("MEAS")

    def stop_logging(self) -> None:
        """Stop measurement (STOP command)."""
        self.write("STOP")

    def get_logging_status(self) -> tuple[int, int]:
        """Check measurement status (STAT? command).

        Returns:
            (status, count) where status:
            -  0: measuring in progress
            -  1: measurement completed
            - -1: stopped / forced stop
        """
        raw = self.query("STAT?")
        parts = raw.split(",")
        return int(parts[0]), int(parts[1])

    def get_error(self) -> tuple[int, str]:
        """Read the MPM error queue with ``ERR?``.

        Returns:
            ``(code, message)``. Code 0 means no instrument error.
        """
        raw = self.query("ERR?")
        if "," in raw:
            code_text, message = raw.split(",", 1)
        else:
            code_text, message = raw, ""
        return int(code_text.strip()), message.strip()

    def assert_no_error(self) -> None:
        """Raise if the MPM reports a non-zero error state."""
        code, message = self.get_error()
        if code != 0:
            raise InstrumentOperationError(
                f"MPM error {code}: {message}. Stop scanning and clear the "
                "instrument state; a physical MPM restart may be required.",
                error_code=code,
            )

    def get_channel_logging_data(self, module: int, channel: int) -> list[float]:
        """Retrieve logged power data for a specific module/channel.

        Uses LOGG? command which returns IEEE 488.2 binary block format
        with single-precision floats (4 bytes each, LSB first).

        Args:
            module: Module number (0-4).
            channel: Port number (1-4).
        """
        return self._read_logg_data(module, channel)

    def get_module_logging_data(self, module: int) -> list[list[float]]:
        """Retrieve logged data for all channels of a module.

        Queries each channel individually.
        """
        result: list[list[float]] = []
        for ch in range(1, 5):
            result.append(self._read_logg_data(module, ch))
        return result

    def _read_logg_data(self, module: int, channel: int) -> list[float]:
        """Read binary LOGG? data and parse IEEE 754 floats."""
        assert self._resource is not None

        # Increase timeout for large binary transfers (4004+ bytes)
        old_timeout = self._resource.timeout
        self._resource.timeout = 30000  # 30 seconds

        try:
            # Send command
            self._resource.write(f"LOGG? {module},{channel}")

            # Read raw bytes — LOGG? returns IEEE 488.2 definite block
            raw = self._resource.read_raw()

            # Parse: #<digits_count><byte_count><binary_data>
            if raw[0:1] != b"#":
                # Fallback: try ASCII comma-separated (some firmware versions)
                text = raw.decode("ascii", errors="replace").strip()
                return [float(v) for v in text.split(",") if v.strip()]

            digits_count = int(raw[1:2])
            byte_count = int(raw[2 : 2 + digits_count])
            data_start = 2 + digits_count
            expected_total = data_start + byte_count

            # GPIB may fragment the transfer — accumulate until complete
            while len(raw) < expected_total:
                chunk = self._resource.read_raw()
                if not chunk:
                    break
                raw += chunk

            binary_data = raw[data_start : data_start + byte_count]

            # Parse IEEE 754 single-precision floats (4 bytes each, LSB first)
            n_floats = byte_count // 4
            values = struct.unpack(f"<{n_floats}f", binary_data)
            return list(values)
        finally:
            self._resource.timeout = old_timeout

    # --- Zeroing ---

    def perform_zeroing(self) -> None:
        """Run zeroing to remove electrical DC offset.

        Takes about 3 seconds — do not send other commands during that time.
        """
        self.write("ZERO")

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
        return 1
