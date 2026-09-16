#!/usr/bin/env python3
"""Santec 仪器控制 Flask 服务器

运行在 Windows 电脑上，通过 GPIB 控制 TSL-550 激光器和 MPM-210 功率计。
Mac 电脑通过网络请求此服务器来执行扫描操作。

用法:
    python server.py [--host 0.0.0.0] [--port 5000] [--tsl GPIB3::1::INSTR] [--mpm GPIB0::16::INSTR]

前提条件 (Windows):
    - NI-VISA 运行时已安装
    - pip install flask pyvisa numpy
"""

from __future__ import annotations

import argparse
import logging
import os
import threading
import time
from functools import wraps
from flask import Flask, request, jsonify

try:
    import pyvisa
    from santecpro.instruments.tsl import TSLInstrument
    from santecpro.instruments.mpm import MPMInstrument
    from santecpro.scanner import Scanner
except Exception:  # DLL/STSProcess server mode does not require pyvisa.
    pyvisa = None
    TSLInstrument = MPMInstrument = Scanner = None

import config
from santec_dll_backend.instruments import DllMpm, DllTsl, ScanCancelled
from santec_dll_backend.scanner import run_stsprocess_scan
from stsprocess_api import build_sts_scan_settings, sts_scan_result_to_dict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "server.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
logger = logging.getLogger("santec_server")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------

rm = None
tsl: TSLInstrument | None = None
mpm: MPMInstrument | None = None
scanner: Scanner | None = None
tsl_idn: str | None = None
mpm_idn: str | None = None
instrument_lock = threading.RLock()
state_lock = threading.RLock()
scan_cancel = threading.Event()
laser_start_requests: set[str] = set()


def exclusive_instruments(func):
    """Reject competing requests instead of queuing commands behind a scan."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not instrument_lock.acquire(blocking=False):
            return jsonify({"error": "Instruments are busy."}), 409
        try:
            return func(*args, **kwargs)
        finally:
            instrument_lock.release()
    return wrapper

scan_state: dict = {
    "running": False,
    "phase": "idle",
    "started_at": None,
    "finished_at": None,
    "last_error": None,
    "last_result_points": None,
    "params": None,
}


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _require_connected():
    """检查仪器是否已连接，未连接则返回错误响应。"""
    if tsl is None or mpm is None:
        return jsonify({"error": "Instruments not connected. Call /api/connect first."}), 400
    return None


def _scan_result_to_dict(result) -> dict:
    """将 ScanResult 转为可 JSON 序列化的 dict。"""
    return {
        "wavelengths": result.wavelengths.tolist(),
        "powers": result.powers.tolist(),
        "monitor_powers": result.monitor_powers.tolist(),
        "scan_params": result.scan_params,
        "timestamp": result.timestamp,
        "mpm_range": result.mpm_range,
    }


def _set_scan_state(**updates) -> None:
    with state_lock:
        scan_state.update(updates)


# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------

@app.route("/api/status", methods=["GET"])
def status():
    """返回服务器状态和仪器连接信息。"""
    return jsonify({
        "status": "running",
        "tsl_connected": tsl is not None and tsl.is_connected,
        "mpm_connected": mpm is not None and mpm.is_connected,
        "tsl_idn": tsl_idn,
        "mpm_idn": mpm_idn,
        "scan": scan_state,
        "log_path": LOG_PATH,
    })


@app.route("/api/scan/state", methods=["GET"])
def get_scan_state():
    """返回当前扫描状态，不访问仪器。"""
    return jsonify(scan_state)


@app.route("/api/logs", methods=["GET"])
def get_logs():
    """返回 server.log 的尾部内容，便于 Mac 端查看 Windows 扫描进度。"""
    lines = int(request.args.get("lines", 200))
    lines = max(1, min(lines, 2000))
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            tail = f.readlines()[-lines:]
    except FileNotFoundError:
        tail = []
    return jsonify({"log_path": LOG_PATH, "lines": tail})


@app.route("/api/connect", methods=["POST"])
@exclusive_instruments
def connect():
    """连接 TSL 和 MPM 仪器。"""
    global rm, tsl, mpm, scanner, tsl_idn, mpm_idn

    if pyvisa is None or TSLInstrument is None or MPMInstrument is None or Scanner is None:
        return jsonify({"error": "pyvisa SCPI backend is not available on this server."}), 500

    data = request.get_json(silent=True) or {}
    tsl_addr = data.get("tsl_address") or config.TSL_ADDRESS
    mpm_addr = data.get("mpm_address") or config.MPM_ADDRESS

    try:
        with instrument_lock:
            rm = pyvisa.ResourceManager()
            tsl = TSLInstrument(rm, trace=True)
            tsl.connect(tsl_addr)
            tsl_idn = tsl.idn
            logger.info("TSL connected: %s", tsl_idn)

            mpm = MPMInstrument(rm, trace=True)
            mpm.connect(mpm_addr)
            mpm_idn = mpm.idn
            logger.info("MPM connected: %s", mpm_idn)

            scanner = Scanner(tsl, mpm)

        return jsonify({
            "status": "ok",
            "tsl_idn": tsl_idn,
            "mpm_idn": mpm_idn,
        })
    except Exception as e:
        logger.exception("Connection failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/disconnect", methods=["POST"])
@exclusive_instruments
def disconnect():
    """断开仪器连接。"""
    global rm, tsl, mpm, scanner, tsl_idn, mpm_idn
    try:
        with instrument_lock:
            if tsl:
                tsl.disconnect()
            if mpm:
                mpm.disconnect()
            if rm:
                rm.close()
    except Exception:
        pass
    tsl = mpm = scanner = rm = None
    tsl_idn = mpm_idn = None
    return jsonify({"status": "ok"})


@app.route("/api/idn", methods=["GET"])
@exclusive_instruments
def idn():
    """获取仪器识别信息。"""
    err = _require_connected()
    if err:
        return err
    return jsonify({
        "tsl_idn": tsl_idn,
        "mpm_idn": mpm_idn,
    })


@app.route("/api/configure", methods=["POST"])
@exclusive_instruments
def configure():
    """配置扫描参数。"""
    err = _require_connected()
    if err:
        return err

    data = request.get_json()
    try:
        with instrument_lock:
            logger.info("Configure request: %s", data)
            scanner.configure(
                start_wl=data["start_wl"],
                stop_wl=data["stop_wl"],
                step=data["step"],
                speed=data["speed"],
                power=data["power"],
                sweep_mode=data.get("sweep_mode", 1),  # 1 = Continuous One-way
                ranges=data.get("ranges", [1]),
                mpm_channel=data.get("mpm_channel", 1),
                mpm_module=data.get("mpm_module", 1),
                mpm_averaging_time_ms=data.get("mpm_averaging_time_ms", 0.01),
            )
            _set_scan_state(params=data, last_error=None, phase="configured")
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.exception("Configure failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/scan/single", methods=["POST"])
@exclusive_instruments
def scan_single():
    """执行单次扫描并返回数据。"""
    err = _require_connected()
    if err:
        return err

    data = request.get_json() or {}
    mpm_range = data.get("mpm_range", 1)

    try:
        with instrument_lock:
            if scan_state.get("running"):
                return jsonify({"error": "A scan is already running."}), 409
            _set_scan_state(
                running=True,
                phase="running",
                started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                finished_at=None,
                last_error=None,
                last_result_points=None,
            )
            logger.info("Single scan request: mpm_range=%s", mpm_range)
            result = scanner.run_single_scan(mpm_range=mpm_range, plot=False, save_csv=None)
            _set_scan_state(
                running=False,
                phase="completed",
                finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                last_result_points=len(result.powers),
            )
        return jsonify(_scan_result_to_dict(result))
    except Exception as e:
        _set_scan_state(
            running=False,
            phase="error",
            finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            last_error=str(e),
        )
        logger.exception("Single scan failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/scan/stsprocess", methods=["POST"])
@exclusive_instruments
def scan_stsprocess():
    """执行 DLL/STSProcess 扫描并返回重采样后的目标点表。"""
    data = request.get_json() or {}
    try:
        with instrument_lock:
            if scan_state.get("running"):
                return jsonify({"error": "A scan is already running."}), 409
            settings = build_sts_scan_settings(data, BASE_DIR)
            scan_cancel.clear()
            _set_scan_state(
                running=True,
                phase="stsprocess_running",
                started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                finished_at=None,
                last_error=None,
                last_result_points=None,
                params=data,
            )
            logger.info("STSProcess scan request: %s", data)
            result = run_stsprocess_scan(settings, cancel_event=scan_cancel)
            _set_scan_state(
                running=False,
                phase="completed",
                finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                last_result_points=result.target_points,
                last_error=None,
            )
        return jsonify(sts_scan_result_to_dict(result, data))
    except Exception as e:
        _set_scan_state(
            running=False,
            phase="error",
            finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            last_error=str(e),
        )
        if isinstance(e, ScanCancelled):
            _set_scan_state(phase="cancelled")
            return jsonify({"error": str(e), "cancelled": True}), 409
        logger.exception("STSProcess scan failed")
        return jsonify({"error": str(e)}), 400 if isinstance(e, (ValueError, KeyError)) else 500


@app.route("/api/scan/reference", methods=["POST"])
@exclusive_instruments
def scan_reference():
    """执行参考扫描。"""
    err = _require_connected()
    if err:
        return err

    data = request.get_json() or {}
    mpm_range = data.get("mpm_range", None)

    try:
        result = scanner.run_reference_scan(mpm_range=mpm_range)
        return jsonify(_scan_result_to_dict(result))
    except Exception as e:
        logger.exception("Reference scan failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/scan/multi_range", methods=["POST"])
@exclusive_instruments
def scan_multi_range():
    """执行多 range 扫描并返回合并结果。"""
    err = _require_connected()
    if err:
        return err

    data = request.get_json() or {}
    ranges = data.get("ranges", None)

    try:
        result = scanner.run_multi_range_scan_merged(ranges=ranges, plot=False, save_raw_csv=None)
        return jsonify(_scan_result_to_dict(result))
    except Exception as e:
        logger.exception("Multi-range scan failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/scan/il", methods=["POST"])
@exclusive_instruments
def scan_il():
    """执行完整 IL 测量（参考扫描 + 多 range 测量扫描）。"""
    err = _require_connected()
    if err:
        return err

    data = request.get_json() or {}
    ranges = data.get("ranges", None)

    try:
        il_result = scanner.run_il_measurement(ranges=ranges, plot=False, save_raw_csv=None, save_loss_csv=None)
        return jsonify({
            "reference": _scan_result_to_dict(il_result.reference),
            "measurement": _scan_result_to_dict(il_result.measurement),
            "il": il_result.il.tolist(),
            "wavelengths": il_result.wavelengths.tolist(),
        })
    except Exception as e:
        logger.exception("IL measurement failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/tsl/command", methods=["POST"])
@exclusive_instruments
def tsl_command():
    """直接发送 SCPI 命令到 TSL（用于调试）。"""
    err = _require_connected()
    if err:
        return err

    data = request.get_json()
    cmd = data.get("command", "")
    mode = data.get("mode", "query")  # "query" 或 "write"

    try:
        with instrument_lock:
            if mode == "query":
                response = tsl.query(cmd)
                return jsonify({"response": response})
            else:
                tsl.write(cmd)
                return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/mpm/command", methods=["POST"])
@exclusive_instruments
def mpm_command():
    """直接发送 SCPI 命令到 MPM（用于调试）。"""
    err = _require_connected()
    if err:
        return err

    data = request.get_json()
    cmd = data.get("command", "")
    mode = data.get("mode", "query")  # "query" 或 "write"

    try:
        with instrument_lock:
            if mode == "query":
                response = mpm.query(cmd)
                return jsonify({"response": response})
            else:
                mpm.write(cmd)
                return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/mpm/data", methods=["POST"])
@exclusive_instruments
def mpm_data():
    """读取 MPM 测量数据（LOGG? 二进制格式，转为 JSON 列表）。"""
    err = _require_connected()
    if err:
        return err

    data = request.get_json() or {}
    module = data.get("module", 1)
    channel = data.get("channel", 1)

    try:
        with instrument_lock:
            powers = mpm.get_channel_logging_data(module, channel)
        return jsonify({"powers": powers, "count": len(powers)})
    except Exception as e:
        logger.exception("MPM data read failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/laser/on", methods=["POST"])
@exclusive_instruments
def laser_on():
    """开启激光器和快门。"""
    err = _require_connected()
    if err:
        return err
    with instrument_lock:
        tsl.laser_on()
        tsl.shutter_open()
    return jsonify({"status": "ok"})


@app.route("/api/laser/off", methods=["POST"])
@exclusive_instruments
def laser_off():
    """关闭激光器和快门。"""
    err = _require_connected()
    if err:
        return err
    with instrument_lock:
        tsl.shutter_close()
        tsl.laser_off()
    return jsonify({"status": "ok"})


@app.route("/api/scan/cancel", methods=["POST"])
def cancel_scan():
    with state_lock:
        if not scan_state["running"] or scan_state["phase"] not in ("stsprocess_running", "cancelling"):
            return jsonify({"status": "idle", "requested": False})
        scan_cancel.set()
        scan_state["phase"] = "cancelling"
        return jsonify({"status": "cancelling", "requested": True}), 202


@app.route("/api/dll/check", methods=["POST"])
@exclusive_instruments
def dll_check():
    """Read instrument identity via DLL without changing laser output."""
    global tsl_idn, mpm_idn
    data = request.get_json(silent=True) or {}
    laser = meter = None
    try:
        laser = DllTsl(data.get("tsl_address") or config.TSL_ADDRESS)
        meter = DllMpm(data.get("mpm_address") or config.MPM_ADDRESS)
        laser.connect()
        meter.connect()
        tsl_idn, mpm_idn = laser.idn(), meter.idn()
        return jsonify({"status": "ok", "tsl_idn": tsl_idn, "mpm_idn": mpm_idn,
                        "laser_ready": laser.laser_is_on()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        try:
            if meter is not None:
                meter.disconnect()
        finally:
            if laser is not None:
                laser.disconnect()


@app.route("/api/dll/laser/prepare", methods=["POST"])
@app.route("/api/dll/laser/on", methods=["POST"])
@exclusive_instruments
def dll_laser_on():
    """Start LD once, poll actual readiness, and open shutter only when ready."""
    data = request.get_json(silent=True) or {}
    address = data.get("tsl_address") or config.TSL_ADDRESS
    laser = None
    try:
        laser = DllTsl(address)
        laser.connect()
        ready = laser.laser_is_on()
        if not ready and address not in laser_start_requests:
            laser.laser_on()
            laser_start_requests.add(address)
            ready = laser.laser_is_on()
        if ready:
            laser_start_requests.discard(address)
            laser.shutter_open()
        return jsonify({"ready": ready, "status": "ready" if ready else "warming_up"})
    except Exception as exc:
        logger.exception("Laser initialization failed")
        return jsonify({"error": str(exc)}), 500
    finally:
        if laser is not None:
            laser.disconnect()


@app.route("/api/dll/laser/off", methods=["POST"])
@exclusive_instruments
def dll_laser_off():
    """通过官方 DLL 关闭快门和激光器。"""
    data = request.get_json(silent=True) or {}
    tsl_addr = data.get("tsl_address") or config.TSL_ADDRESS
    try:
        with instrument_lock:
            laser = DllTsl(tsl_addr)
            try:
                laser.connect()
                try:
                    laser.shutter_close()
                finally:
                    laser.laser_off()
                laser_start_requests.discard(tsl_addr)
            finally:
                laser.disconnect()
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.exception("DLL laser off failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/dll/alignment/start", methods=["POST"])
@exclusive_instruments
def dll_alignment_start():
    """Set fixed laser output and return selected MPM channel powers."""
    data = request.get_json(silent=True) or {}
    tsl_addr = data.get("tsl_address") or config.TSL_ADDRESS
    mpm_addr = data.get("mpm_address") or config.MPM_ADDRESS
    module = int(data.get("mpm_module", 0))
    channels = [int(ch) for ch in data.get("mpm_channels", [1])]
    mpm_range = int(data.get("mpm_range", 1))
    power = float(data.get("power", 0.0))
    try:
        with instrument_lock:
            laser = DllTsl(tsl_addr)
            meter = DllMpm(mpm_addr)
            try:
                laser.connect()
                meter.connect()
                if not laser.laser_is_on():
                    raise RuntimeError("Laser is not ready; initialize and wait for warmup first.")
                laser.set_power_dbm(power)
                for channel in channels:
                    meter.configure_power_logging(module, channel, mpm_range)
                powers = meter.read_power_channels(module, channels)
            finally:
                try:
                    meter.disconnect()
                finally:
                    laser.disconnect()
        return jsonify({"status": "ok", "powers": {str(ch): p for ch, p in powers.items()}})
    except Exception as e:
        logger.exception("DLL alignment start failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/dll/mpm/powers", methods=["POST"])
@exclusive_instruments
def dll_mpm_powers():
    """Read selected MPM channel powers through the official DLL."""
    data = request.get_json(silent=True) or {}
    mpm_addr = data.get("mpm_address") or config.MPM_ADDRESS
    module = int(data.get("mpm_module", 0))
    channels = [int(ch) for ch in data.get("mpm_channels", [1])]
    try:
        with instrument_lock:
            meter = DllMpm(mpm_addr)
            try:
                meter.connect()
                powers = meter.read_power_channels(module, channels)
            finally:
                meter.disconnect()
        return jsonify({"status": "ok", "powers": {str(ch): p for ch, p in powers.items()}})
    except Exception as e:
        logger.exception("DLL MPM power read failed")
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Santec 仪器控制服务器")
    parser.add_argument("--host", default=config.HOST, help="监听地址 (默认 0.0.0.0)")
    parser.add_argument("--port", type=int, default=config.PORT, help="监听端口 (默认 5000)")
    parser.add_argument("--tsl", default=config.TSL_ADDRESS, help="TSL GPIB 地址")
    parser.add_argument("--mpm", default=config.MPM_ADDRESS, help="MPM GPIB 地址")
    args = parser.parse_args()

    config.TSL_ADDRESS = args.tsl
    config.MPM_ADDRESS = args.mpm

    logger.info("Starting Santec instrument server on %s:%d", args.host, args.port)
    logger.info("TSL address: %s", args.tsl)
    logger.info("MPM address: %s", args.mpm)
    app.run(host=args.host, port=args.port, debug=False)
