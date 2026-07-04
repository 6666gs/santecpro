"""Controller layer shared by the PyQt UI and tests (remote-only).

The client drives a Windows-hosted server over HTTP; there is no local VISA
path here. Direct-to-instrument control lives on the Windows server.
"""

from __future__ import annotations

from dataclasses import dataclass

from santecpro.exporter import save_raw_csv
from santecpro.remote import RemoteScanner
from santecpro.results import ScanResult
from santecpro.server_control import start_windows_server


@dataclass
class ConnectionSettings:
    """Connection inputs from the UI."""

    server_url: str
    tsl_address: str = ""
    mpm_address: str = ""


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
    """Drives the remote Santec server over HTTP for the UI."""

    def __init__(self) -> None:
        self._scanner: RemoteScanner | None = None
        self._tsl_idn = ""
        self._mpm_idn = ""

    @property
    def is_connected(self) -> bool:
        return self._scanner is not None

    def connect(self, settings: ConnectionSettings) -> dict:
        """Connect to the remote server and return its status."""
        self.disconnect()
        scanner = RemoteScanner(settings.server_url)
        self._scanner = scanner
        status = scanner.status()
        self._tsl_idn = status.get("tsl_idn") or ""
        self._mpm_idn = status.get("mpm_idn") or ""
        return status

    def start_remote_server(self, settings: ConnectionSettings) -> dict:
        """Start ``server.py`` on the Windows host over SSH, then report status."""
        start_windows_server(settings.server_url)
        scanner = RemoteScanner(settings.server_url)
        return scanner.status()

    def disconnect(self) -> None:
        """Disconnect from the remote server."""
        if self._scanner is not None:
            try:
                self._scanner.disconnect()
            except Exception:
                pass
        self._scanner = None
        self._tsl_idn = ""
        self._mpm_idn = ""

    def laser_on(self) -> None:
        """Turn on laser output on the remote server."""
        self._require_scanner().laser_on()

    def laser_off(self) -> None:
        """Turn off laser output on the remote server."""
        self._require_scanner().laser_off()

    def run_single_scan(self, settings: ScanSettings) -> ScanResult:
        """Run one STSProcess scan on the remote server."""
        scanner = self._require_scanner()
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
        return self._require_scanner().start_alignment(
            power=power,
            mpm_module=mpm_module,
            mpm_channels=mpm_channels,
            mpm_range=mpm_range,
        )

    def read_alignment_powers(
        self,
        mpm_module: int,
        mpm_channels: tuple[int, ...],
    ) -> dict[int, float]:
        return self._require_scanner().read_alignment_powers(
            mpm_module=mpm_module,
            mpm_channels=mpm_channels,
        )

    def _require_scanner(self) -> RemoteScanner:
        if self._scanner is None:
            raise RuntimeError("Not connected")
        return self._scanner
