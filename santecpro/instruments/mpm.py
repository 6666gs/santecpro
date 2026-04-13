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
