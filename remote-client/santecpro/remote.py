"""Mac 端远程扫描客户端。

通过网络连接 Windows Flask 服务器，控制 Santec TSL-550 + MPM-210 执行扫描。
Mac 端不需要 pyvisa，只需要 requests 库。

用法::

    from santecpro.remote import RemoteScanner

    scanner = RemoteScanner("http://192.168.1.100:5000")
    scanner.connect()
    scanner.configure(start_wl=1550, stop_wl=1560, step=0.01, speed=20, power=0)
    result = scanner.run_single_scan(mpm_range=1, plot=True, save_csv="raw.csv")
    scanner.disconnect()
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import requests

from santecpro.results import ScanResult, ILMeasurement

logger = logging.getLogger(__name__)


class RemoteScanner:
    """通过网络远程控制 Santec 扫描的客户端。

    连接到运行在 Windows 上的 Flask 服务器，发送扫描指令并接收数据。
    数据处理（merge、IL 计算、绘图、导出）在 Mac 端完成。
    """

    def __init__(self, server_url: str, timeout: float = 300.0) -> None:
        """
        Args:
            server_url: Windows Flask 服务器地址，例如 "http://192.168.1.100:5000"
            timeout: HTTP 请求超时时间（秒），扫描操作需要较长时间。
        """
        self._url = server_url.rstrip("/")
        self._timeout = timeout
        self._tsl_idn: str = ""
        self._mpm_idn: str = ""

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    def connect(
        self,
        tsl_address: str = "GPIB3::1::INSTR",
        mpm_address: str = "GPIB0::16::INSTR",
    ) -> None:
        """连接到远程仪器。

        Args:
            tsl_address: TSL 的 GPIB 地址。
            mpm_address: MPM 的 GPIB 地址。
        """
        resp = self._post("/api/connect", {
            "tsl_address": tsl_address,
            "mpm_address": mpm_address,
        })
        self._tsl_idn = resp.get("tsl_idn", "")
        self._mpm_idn = resp.get("mpm_idn", "")
        logger.info("Connected: TSL=%s, MPM=%s", self._tsl_idn, self._mpm_idn)

    def disconnect(self) -> None:
        """断开远程仪器连接。"""
        self._post("/api/disconnect")
        logger.info("Disconnected")

    def status(self) -> dict:
        """查询服务器状态。"""
        return self._get("/api/status")

    # ------------------------------------------------------------------
    # 扫描操作
    # ------------------------------------------------------------------

    def configure(
        self,
        start_wl: float,
        stop_wl: float,
        step: float,
        speed: float,
        power: float,
        sweep_mode: int = 1,
        ranges: list[int] | None = None,
        mpm_channel: int = 1,
        mpm_module: int = 1,
        mpm_averaging_time_ms: float = 0.01,
    ) -> None:
        """配置扫描参数（发送到 Windows 服务器执行）。"""
        self._post("/api/configure", {
            "start_wl": start_wl,
            "stop_wl": stop_wl,
            "step": step,
            "speed": speed,
            "power": power,
            "sweep_mode": sweep_mode,
            "ranges": ranges or [1],
            "mpm_channel": mpm_channel,
            "mpm_module": mpm_module,
            "mpm_averaging_time_ms": mpm_averaging_time_ms,
        })
        logger.info("Configured: %s-%s nm, step=%s nm, speed=%s nm/s, power=%s dBm",
                     start_wl, stop_wl, step, speed, power)

    def run_single_scan(
        self,
        mpm_range: int = 1,
        plot: bool = True,
        save_csv: str | None = None,
    ) -> ScanResult:
        """执行单次扫描。

        扫描在 Windows 服务器上执行，数据传回 Mac 端后转为 ScanResult。
        绘图和 CSV 导出在 Mac 端完成。
        """
        data = self._post("/api/scan/single", {"mpm_range": mpm_range})
        result = self._dict_to_scan_result(data)

        if plot:
            from santecpro.plotter import plot_scan_result
            plot_scan_result(result)

        if save_csv:
            from santecpro.exporter import save_raw_csv
            save_raw_csv(result, self._tsl_idn, self._mpm_idn, save_csv)

        return result

    def run_stsprocess_scan(
        self,
        start_wl: float,
        stop_wl: float,
        step: float,
        speed: float,
        power: float = 0.0,
        mpm_module: int = 0,
        mpm_channel: int = 1,
        mpm_channels: list[int] | tuple[int, ...] | None = None,
        mpm_range: int = 1,
        mpm_averaging_time_ms: float = 0.01,
        csv_name: str = "",
        plot: bool = True,
        save_csv: str | None = None,
    ) -> ScanResult:
        """Run a Windows-side DLL/STSProcess scan and return rescaled data."""
        payload = {
            "start_wl": start_wl,
            "stop_wl": stop_wl,
            "step": step,
            "speed": speed,
            "power": power,
            "mpm_module": mpm_module,
            "mpm_channel": mpm_channel,
            "mpm_range": mpm_range,
            "mpm_averaging_time_ms": mpm_averaging_time_ms,
            "csv_name": csv_name,
        }
        if mpm_channels is not None:
            payload["mpm_channels"] = list(mpm_channels)
        data = self._post("/api/scan/stsprocess", payload)
        result = self._dict_to_scan_result(data)
        result.scan_params["csv_path"] = data.get("csv_path", "")
        result.scan_params["raw_points"] = data.get("raw_points")
        result.scan_params["actual_step"] = data.get("actual_step")

        if plot:
            from santecpro.plotter import plot_scan_result
            plot_scan_result(result)

        if save_csv:
            from santecpro.exporter import save_raw_csv
            save_raw_csv(result, self._tsl_idn, self._mpm_idn, save_csv)

        return result

    def run_reference_scan(
        self,
        mpm_range: int | None = None,
        plot: bool = True,
        save_csv: str | None = None,
    ) -> ScanResult:
        """执行参考扫描。"""
        payload = {}
        if mpm_range is not None:
            payload["mpm_range"] = mpm_range
        data = self._post("/api/scan/reference", payload)
        result = self._dict_to_scan_result(data)

        if plot:
            from santecpro.plotter import plot_scan_result
            plot_scan_result(result)

        if save_csv:
            from santecpro.exporter import save_raw_csv
            save_raw_csv(result, self._tsl_idn, self._mpm_idn, save_csv)

        return result

    def run_multi_range_scan(
        self,
        ranges: list[int] | None = None,
        plot: bool = True,
        save_raw_csv: str | None = None,
    ) -> ScanResult:
        """执行多 range 扫描并返回合并结果。"""
        payload = {}
        if ranges is not None:
            payload["ranges"] = ranges
        data = self._post("/api/scan/multi_range", payload)
        result = self._dict_to_scan_result(data)

        if plot:
            from santecpro.plotter import plot_scan_result
            plot_scan_result(result)

        if save_raw_csv:
            from santecpro.exporter import save_raw_csv
            save_raw_csv(result, self._tsl_idn, self._mpm_idn, save_raw_csv)

        return result

    def run_il_measurement(
        self,
        ranges: list[int] | None = None,
        plot: bool = True,
        save_raw_csv: str | None = None,
        save_loss_csv: str | None = None,
    ) -> ILMeasurement:
        """执行完整 IL 测量（参考扫描 + 多 range 测量扫描 + IL 计算）。

        扫描在 Windows 上执行，IL 计算在 Mac 上完成。
        """
        payload = {}
        if ranges is not None:
            payload["ranges"] = ranges
        data = self._post("/api/scan/il", payload)

        reference = self._dict_to_scan_result(data["reference"])
        measurement = self._dict_to_scan_result(data["measurement"])
        il = np.array(data["il"], dtype=float)
        wavelengths = np.array(data["wavelengths"], dtype=float)

        result = ILMeasurement(
            reference=reference,
            measurement=measurement,
            il=il,
            wavelengths=wavelengths,
        )

        if plot:
            from santecpro.plotter import plot_il_result
            plot_il_result(result)

        if save_raw_csv:
            from santecpro.exporter import save_raw_csv
            save_raw_csv(measurement, self._tsl_idn, self._mpm_idn, save_raw_csv)

        if save_loss_csv:
            from santecpro.exporter import save_loss_csv
            save_loss_csv(result, self._tsl_idn, self._mpm_idn, save_loss_csv)

        return result

    # ------------------------------------------------------------------
    # 激光器控制
    # ------------------------------------------------------------------

    def laser_on(self) -> None:
        """开启激光器和快门。"""
        self._post("/api/dll/laser/on")
        logger.info("Laser ON, Shutter OPEN")

    def laser_off(self) -> None:
        """关闭激光器和快门。"""
        self._post("/api/dll/laser/off")
        logger.info("Shutter CLOSE, Laser OFF")

    def start_alignment(
        self,
        power: float,
        mpm_module: int = 0,
        mpm_channels: list[int] | tuple[int, ...] = (1,),
        mpm_range: int = 1,
    ) -> dict[int, float]:
        """Set fixed laser output and read selected channel powers."""
        data = self._post("/api/dll/alignment/start", {
            "power": power,
            "mpm_module": mpm_module,
            "mpm_channels": list(mpm_channels),
            "mpm_range": mpm_range,
        })
        return {int(ch): float(power) for ch, power in data.get("powers", {}).items()}

    def read_alignment_powers(
        self,
        mpm_module: int = 0,
        mpm_channels: list[int] | tuple[int, ...] = (1,),
    ) -> dict[int, float]:
        """Read current powers for selected channels."""
        data = self._post("/api/dll/mpm/powers", {
            "mpm_module": mpm_module,
            "mpm_channels": list(mpm_channels),
        })
        return {int(ch): float(power) for ch, power in data.get("powers", {}).items()}

    # ------------------------------------------------------------------
    # 直接 SCPI 命令（调试用）
    # ------------------------------------------------------------------

    def tsl_query(self, command: str) -> str:
        """直接向 TSL 发送 SCPI 查询命令。"""
        resp = self._post("/api/tsl/command", {"command": command, "mode": "query"})
        return resp.get("response", "")

    def tsl_write(self, command: str) -> None:
        """直接向 TSL 发送 SCPI 写入命令。"""
        self._post("/api/tsl/command", {"command": command, "mode": "write"})

    def mpm_query(self, command: str) -> str:
        """直接向 MPM 发送 SCPI 查询命令。"""
        resp = self._post("/api/mpm/command", {"command": command, "mode": "query"})
        return resp.get("response", "")

    def mpm_write(self, command: str) -> None:
        """直接向 MPM 发送 SCPI 写入命令。"""
        self._post("/api/mpm/command", {"command": command, "mode": "write"})

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _post(self, path: str, data: dict | None = None) -> dict:
        """发送 POST 请求到服务器。"""
        url = f"{self._url}{path}"
        try:
            resp = requests.post(url, json=data, timeout=self._timeout)
            resp.raise_for_status()
            result = resp.json()
            if "error" in result:
                raise RuntimeError(f"Server error: {result['error']}")
            return result
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Request to {url} timed out ({self._timeout}s)")
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Cannot connect to server at {self._url}")

    def _get(self, path: str) -> dict:
        """发送 GET 请求到服务器。"""
        url = f"{self._url}{path}"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Cannot connect to server at {self._url}")

    @staticmethod
    def _dict_to_scan_result(data: dict) -> ScanResult:
        """将服务器返回的 dict 转为 ScanResult 对象。"""
        return ScanResult(
            wavelengths=np.array(data["wavelengths"], dtype=float),
            powers=np.array(data["powers"], dtype=float),
            monitor_powers=np.array(data["monitor_powers"], dtype=float),
            scan_params=data.get("scan_params", {}),
            timestamp=data.get("timestamp", ""),
            mpm_range=data.get("mpm_range", 1),
            channel_powers={
                int(ch): np.array(values, dtype=float)
                for ch, values in data.get("channel_powers", {}).items()
            },
        )
