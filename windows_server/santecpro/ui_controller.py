"""Controller layer shared by the PyQt UI and tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import pyvisa
except Exception:  # pragma: no cover - local mode reports a clear error later
    pyvisa = None

from santecpro.exporter import save_raw_csv
from santecpro.instruments.mpm import MPMInstrument
from santecpro.instruments.tsl import TSLInstrument
from santecpro.remote import RemoteScanner
from santecpro.server_control import start_windows_server
from santecpro.scanner import ScanResult, Scanner


@dataclass
class ConnectionSettings:
    """Connection inputs from the UI."""

    mode: str
    server_url: str
    tsl_address: str
    mpm_address: str


@dataclass
class ScanSettings:
    """Scan parameter inputs from the UI."""

    start_wl: float
    stop_wl: float
    step: float
    speed: float
    power: float
    sweep_mode: int
    mpm_range: int
    mpm_module: int
    mpm_channel: int
    mpm_averaging_time_ms: float
    mpm_channels: tuple[int, ...] = ()


class ScanUiController:
    """Unifies remote and local instrument control for the UI."""

    def __init__(self) -> None:
        self._mode = ""
        self._scanner: RemoteScanner | Scanner | None = None
        self._rm: Any = None
        self._tsl: TSLInstrument | None = None
        self._mpm: MPMInstrument | None = None
        self._tsl_idn = ""
        self._mpm_idn = ""

    @property
    def is_connected(self) -> bool:
        return self._scanner is not None

    def connect(self, settings: ConnectionSettings) -> dict:
        """Connect using either remote HTTP or local VISA mode."""
        self.disconnect()
        mode = settings.mode.lower()
        if mode == "remote":
            scanner = RemoteScanner(settings.server_url)
            self._scanner = scanner
            self._mode = mode
            status = scanner.status()
            self._tsl_idn = status.get("tsl_idn") or ""
            self._mpm_idn = status.get("mpm_idn") or ""
            return status

        if mode == "local":
            if pyvisa is None:
                raise RuntimeError("pyvisa is required for local mode")
            self._rm = pyvisa.ResourceManager()
            self._tsl = TSLInstrument(self._rm)
            self._mpm = MPMInstrument(self._rm)
            self._tsl.connect(settings.tsl_address)
            self._mpm.connect(settings.mpm_address)
            self._scanner = Scanner(self._tsl, self._mpm)
            self._mode = mode
            self._tsl_idn = self._tsl.idn
            self._mpm_idn = self._mpm.idn
            return {
                "mode": "local",
                "tsl_connected": True,
                "mpm_connected": True,
                "tsl_idn": self._tsl_idn,
                "mpm_idn": self._mpm_idn,
            }

        raise ValueError(f"Unknown connection mode: {settings.mode}")

    def start_remote_server(self, settings: ConnectionSettings) -> dict:
        if settings.mode.lower() != "remote":
            raise RuntimeError("Remote server start is only available in remote mode")
        start_windows_server(settings.server_url)
        scanner = RemoteScanner(settings.server_url)
        return scanner.status()

    def disconnect(self) -> None:
        """Disconnect instruments and release local resources."""
        if self._mode == "remote" and self._scanner is not None:
            try:
                self._scanner.disconnect()
            except Exception:
                pass
        else:
            if self._tsl is not None:
                try:
                    self._tsl.disconnect()
                except Exception:
                    pass
            if self._mpm is not None:
                try:
                    self._mpm.disconnect()
                except Exception:
                    pass
            if self._rm is not None:
                try:
                    self._rm.close()
                except Exception:
                    pass

        self._scanner = None
        self._rm = None
        self._tsl = None
        self._mpm = None
        self._mode = ""
        self._tsl_idn = ""
        self._mpm_idn = ""

    def laser_on(self) -> None:
        """Turn on laser output and open shutter."""
        scanner = self._require_scanner()
        if self._mode == "remote":
            scanner.laser_on()
            return
        assert self._tsl is not None
        self._tsl.shutter_open()
        self._tsl.laser_on()

    def laser_off(self) -> None:
        """Close shutter and turn off laser output."""
        scanner = self._require_scanner()
        if self._mode == "remote":
            scanner.laser_off()
            return
        assert self._tsl is not None
        self._tsl.shutter_close()
        self._tsl.laser_off()

    def run_single_scan(self, settings: ScanSettings) -> ScanResult:
        """Configure instruments and run one scan."""
        scanner = self._require_scanner()
        if self._mode == "remote":
            return scanner.run_stsprocess_scan(
                start_wl=settings.start_wl,
                stop_wl=settings.stop_wl,
                step=settings.step,
                speed=settings.speed,
                power=settings.power,
                mpm_module=settings.mpm_module,
                mpm_channel=settings.mpm_channel,
                mpm_channels=settings.mpm_channels,
                mpm_range=settings.mpm_range,
                mpm_averaging_time_ms=settings.mpm_averaging_time_ms,
                csv_name="",
                plot=False,
                save_csv=None,
            )
        scanner.configure(
            start_wl=settings.start_wl,
            stop_wl=settings.stop_wl,
            step=settings.step,
            speed=settings.speed,
            power=settings.power,
            sweep_mode=settings.sweep_mode,
            ranges=[settings.mpm_range],
            mpm_module=settings.mpm_module,
            mpm_channel=settings.mpm_channel,
            mpm_averaging_time_ms=settings.mpm_averaging_time_ms,
        )
        return scanner.run_single_scan(
            mpm_range=settings.mpm_range,
            plot=False,
            save_csv=None,
        )

    def save_scan_csv(self, result: ScanResult, path: str) -> None:
        """Save the last scan result to CSV."""
        save_raw_csv(result, self._tsl_idn, self._mpm_idn, path)

    def start_alignment(
        self,
        power: float,
        mpm_module: int,
        mpm_channels: tuple[int, ...],
        mpm_range: int,
    ) -> dict[int, float]:
        scanner = self._require_scanner()
        if self._mode == "remote":
            return scanner.start_alignment(
                power=power,
                mpm_module=mpm_module,
                mpm_channels=mpm_channels,
                mpm_range=mpm_range,
            )
        assert self._tsl is not None and self._mpm is not None
        self._tsl.set_power(power)
        self._tsl.shutter_open()
        self._tsl.laser_on()
        return {channel: self._mpm.get_power_channel(mpm_module, channel) for channel in mpm_channels}

    def read_alignment_powers(
        self,
        mpm_module: int,
        mpm_channels: tuple[int, ...],
    ) -> dict[int, float]:
        scanner = self._require_scanner()
        if self._mode == "remote":
            return scanner.read_alignment_powers(
                mpm_module=mpm_module,
                mpm_channels=mpm_channels,
            )
        assert self._mpm is not None
        return {channel: self._mpm.get_power_channel(mpm_module, channel) for channel in mpm_channels}

    def _require_scanner(self) -> RemoteScanner | Scanner:
        if self._scanner is None:
            raise RuntimeError("Not connected")
        return self._scanner
