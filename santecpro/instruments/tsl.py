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
