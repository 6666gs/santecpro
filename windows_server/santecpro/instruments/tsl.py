"""TSL-550 Tunable Laser instrument driver.

SCPI Command Set 1 (IEEE-488.2 compliant) — used when GPIB command
setting is configured to 'SCPI'.

All commands use the ``[:SOURce]`` root which is the default, so the
prefix can be omitted.
"""

from __future__ import annotations

import struct

from santecpro.instruments.base import BaseInstrument

# Sweep mode numbers (WAV:SWE:MOD parameter)
SWEEP_MODE_STEP_ONE_WAY = 0
SWEEP_MODE_CONT_ONE_WAY = 1
SWEEP_MODE_STEP_TWO_WAY = 2
SWEEP_MODE_CONT_TWO_WAY = 3

# Sweep state numbers (WAV:SWE parameter)
SWEEP_STATE_STOP = 0
SWEEP_STATE_START = 1
SWEEP_STATE_PAUSE = 2
SWEEP_STATE_RESUME = 3

# Sweep status values (WAV:SWE? response)
SWEEP_STATUS_STOP = 0
SWEEP_STATUS_RUNNING = 1
SWEEP_STATUS_PAUSE = 2
SWEEP_STATUS_TRIGGER_STANDBY = 3
SWEEP_STATUS_RETURNING = 4

# Trigger output mode numbers (TRIG:OUTP parameter)
TRIG_OUT_NONE = 0
TRIG_OUT_STOP = 1
TRIG_OUT_START = 2
TRIG_OUT_STEP = 3

MIN_SWEEP_SPEED_NM_PER_S = 1.0


class TSLInstrument(BaseInstrument):
    """Driver for the Santec TSL-550 tunable laser source.

    Communicates via SCPI Command Set 1 over GPIB.
    """

    def connect(self, resource_string: str) -> None:
        """Connect to TSL and send initialization sequence."""
        super().connect(resource_string, terminator="\r", read_terminator="\n")
        self.status_clear()
        self.device_reset()

    # --- Laser diode control ---
    # POW:STAT  — [:SOURce]:POWer:STATe

    def laser_on(self) -> None:
        self.write("POW:STAT 1")

    def laser_off(self) -> None:
        self.write("POW:STAT 0")

    def get_laser_status(self) -> str:
        """Query LD status. Returns '0' (ON) or '1' (OFF)."""
        return self.query("POW:STAT?")

    # --- Shutter control ---
    # POW:SHUT — [:SOURce]:POWer:SHUTter

    def shutter_open(self) -> None:
        self.write("POW:SHUT 0")

    def shutter_close(self) -> None:
        self.write("POW:SHUT 1")

    def get_shutter_status(self) -> str:
        """Query shutter status. Returns '0' (Open) or '1' (Close)."""
        return self.query("POW:SHUT?")

    # --- Power control ---
    # POW:LEV — [:SOURce]:POWer[:LEVel]

    def set_power(self, power_dbm: float) -> None:
        self.write(f"POW:LEV {power_dbm:.2f}")

    def get_power(self) -> float:
        return float(self.query("POW:LEV?"))

    # --- Wavelength control ---
    # WAV — [:SOURce]:WAVelength

    def set_wavelength(self, wl_nm: float) -> None:
        self.write(f"WAV {wl_nm:.6f}")

    def get_wavelength(self) -> float:
        return float(self.query("WAV?"))

    # --- Sweep configuration ---
    # WAV:SWE:* — [:SOURce]:WAVelength:SWEep:*

    def set_sweep_mode(self, mode: int) -> None:
        """Set sweep mode number: 0=Step One-way, 1=Cont One-way,
        2=Step Two-way, 3=Cont Two-way."""
        self.write(f"WAV:SWE:MOD {mode}")

    def get_sweep_mode(self) -> int:
        """Get sweep mode number."""
        return int(float(self.query("WAV:SWE:MOD?")))

    def set_sweep_speed(self, speed: float) -> None:
        """Set sweep speed in nm/s.

        TSL continuous sweep speeds are instrument-table limited. The Santec
        DLL examples expose the allowed table and commonly document 1 nm/s as
        the minimum continuous sweep speed, so values below that are rejected
        before sending the command.
        """
        if speed < MIN_SWEEP_SPEED_NM_PER_S:
            raise ValueError(
                f"TSL sweep speed {speed} nm/s is below the supported minimum "
                f"{MIN_SWEEP_SPEED_NM_PER_S} nm/s for continuous sweeps."
            )
        self.write(f"WAV:SWE:SPE {speed:.1f}")

    def get_sweep_speed(self) -> float:
        return float(self.query("WAV:SWE:SPE?"))

    def set_sweep_start(self, wl: float) -> None:
        """Set sweep start wavelength in nm."""
        self.write(f"WAV:SWE:STAR {wl:.6f}")

    def get_sweep_start(self) -> float:
        """Get sweep start wavelength in nm."""
        return float(self.query("WAV:SWE:STAR?"))

    def set_sweep_stop(self, wl: float) -> None:
        """Set sweep stop wavelength in nm."""
        self.write(f"WAV:SWE:STOP {wl:.6f}")

    def get_sweep_stop(self) -> float:
        """Get sweep stop wavelength in nm."""
        return float(self.query("WAV:SWE:STOP?"))

    def set_sweep_step(self, step: float) -> None:
        """Set sweep step in nm."""
        self.write(f"WAV:SWE:STEP {step:.6f}")

    def get_sweep_step(self) -> float:
        """Get sweep step in nm."""
        return float(self.query("WAV:SWE:STEP?"))

    # --- Sweep execution ---
    # WAV:SWE — [:SOURce]:WAVelength:SWEep[:STATe]

    def start_sweep(self) -> None:
        self.write("WAV:SWE 1")

    def stop_sweep(self) -> None:
        self.write("WAV:SWE 0")

    def pause_sweep(self) -> None:
        self.write("WAV:SWE 2")

    def restart_sweep(self) -> None:
        self.write("WAV:SWE 3")

    def get_sweep_status(self) -> str:
        """Query sweep status: 0=Stop, 1=Running, 2=Pause,
        3=Trigger standby, 4=Returning."""
        return self.query("WAV:SWE?")

    def soft_trigger(self) -> None:
        self.write("WAV:SWE:SOFT")

    # --- Trigger configuration ---
    # TRIG:OUTP — :TRIGger:OUTPut

    def set_trigger_output(self, mode: int) -> None:
        """Set trigger output: 0=None, 1=Stop, 2=Start, 3=Step."""
        self.write(f"TRIG:OUTP {mode}")

    def set_trigger_step_width(self, width_nm: float) -> None:
        """Set trigger output interval in nm (TRIG:OUTP:STEP command).

        Controls the wavelength interval at which trigger pulses are output
        during a sweep. Must match the sweep step for point-by-point triggering.

        Args:
            width_nm: Trigger interval in nm (0.0001–160).
        """
        self.write(f"TRIG:OUTP:STEP {width_nm:.6f}")

    def get_trigger_step_width(self) -> float:
        """Get trigger output interval in nm."""
        return float(self.query("TRIG:OUTP:STEP?"))

    def set_scan_start_mode(self, mode: int) -> None:
        """Set trigger standby mode: 0=Normal, 1=Trigger standby
        (waiting for soft trigger before sweep)."""
        self.write(f"TRIG:INP:STAN {mode}")

    # --- Utility ---

    def status_clear(self) -> None:
        self.write("*CLS")

    def device_reset(self) -> None:
        self.write("*RST")

    def get_logging_data_points(self) -> int:
        """Get number of logged data points (:READout:POINts?)."""
        return int(self.query(":READ:POIN?"))

    def get_power_monitor_data(self) -> list[float]:
        """Read TSL power monitor log data (:READout:DATa?).

        Returns data as floats. Firmware may return either comma-separated
        ASCII values or an IEEE 488.2 definite-length binary block containing
        little-endian IEEE-754 floats.
        """
        assert self._resource is not None
        self._resource.write(":READ:DAT?")
        raw = self._resource.read_raw()

        if raw[0:1] == b"#":
            digits_count = int(raw[1:2])
            byte_count = int(raw[2 : 2 + digits_count])
            data_start = 2 + digits_count
            expected_total = data_start + byte_count

            while len(raw) < expected_total:
                chunk = self._resource.read_raw()
                if not chunk:
                    break
                raw += chunk

            binary_data = raw[data_start : data_start + byte_count]
            n_floats = byte_count // 4
            return list(struct.unpack(f"<{n_floats}f", binary_data))

        text = raw.decode("ascii", errors="strict").strip()
        return [float(v) for v in text.split(",") if v.strip()]

    def configure_sweep(
        self, start_wl: float, stop_wl: float, step: float, speed: float
    ) -> None:
        """Convenience method to set all sweep parameters at once."""
        self.set_sweep_start(start_wl)
        self.set_sweep_stop(stop_wl)
        self.set_sweep_step(step)
        self.set_sweep_speed(speed)
