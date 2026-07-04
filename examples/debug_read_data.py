#!/usr/bin/env python3
"""读取 MPM 缓冲区数据、保存 CSV、绘图。

前提：已经通过 debug_trigger_sweep.py 完成了一次成功的扫描，
      MPM 缓冲区里有数据（STAT=1,1001）。

用法:
    python examples/debug_read_data.py
"""

import csv
import struct
import time
from datetime import datetime, timezone

import requests
import numpy as np

SERVER = "http://192.168.1.103:5000"

# 扫描参数（与 debug_trigger_sweep.py 一致）
START_WL = 1550.0
STOP_WL = 1560.0
STEP = 0.01
SPEED = 2.0

# 保存文件名
CSV_FILE = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"


def api(path, data=None, timeout=30):
    resp = requests.post(f"{SERVER}{path}", json=data, timeout=timeout)
    result = resp.json()
    if "error" in result:
        print(f"    ERROR: {result['error']}")
        return None
    return result


def main():
    result = api(
        "/api/connect",
        {
            "tsl_address": "GPIB3::1::INSTR",
            "mpm_address": "GPIB0::16::INSTR",
        },
    )
    if not result:
        return
    print(f"    TSL: {result.get('tsl_idn', '?')}")
    print(f"    MPM: {result.get('mpm_idn', '?')}")
    print("=" * 60)
    print("  读取扫描数据")
    print("=" * 60)

    # 检查 MPM 状态
    stat_resp = api("/api/mpm/command", {"command": "STAT?", "mode": "query"})
    if stat_resp:
        stat = stat_resp.get("response", "")
        print(f"    MPM STAT: {stat}")
        if stat.startswith("1"):
            count = stat.split(",")[1] if "," in stat else "?"
            print(f"    MPM has {count} data points ready to read")
        else:
            print("    WARNING: MPM measurement not completed!")

    logn_resp = api("/api/mpm/command", {"command": "LOGN?", "mode": "query"})
    if logn_resp:
        print(f"    MPM LOGN: {logn_resp.get('response', '?')}")

    # 通过服务器的数据读取端点获取数据
    # 因为 LOGG? 返回二进制数据，不能直接用 command 端点
    # 我们用 MPM driver 的 get_channel_logging_data 方法
    print("\n    Reading MPM data via /api/mpm/data ...")

    try:
        resp = requests.post(
            f"{SERVER}/api/mpm/data",
            json={"module": 1, "channel": 1},
            timeout=30,
        )
        result = resp.json()

        if "error" in result:
            print(f"    ERROR: {result['error']}")
            print(
                "    NOTE: Server needs /api/mpm/data endpoint. Trying direct command..."
            )

            # 尝试通过 command 端点读取（可能不支持二进制）
            data_resp = api(
                "/api/mpm/command", {"command": "LOGG? 1,1", "mode": "query"}
            )
            print(f"    LOGG? response type: {type(data_resp)}")
            print(f"    Response (first 200 chars): {str(data_resp)[:200]}")
            return

        powers = result.get("powers", [])
        print(f"    Got {len(powers)} power values")

    except Exception as e:
        print(f"    Failed to read MPM data: {e}")
        print("    Server may not have /api/mpm/data endpoint yet")
        return

    # 读取 TSL power monitor 数据
    print("\n    Reading TSL power monitor data ...")
    try:
        mon_resp = api("/api/tsl/command", {"command": ":READ:DAT?", "mode": "query"})
        if mon_resp:
            mon_raw = mon_resp.get("response", "")
            monitor_powers = [float(v) for v in mon_raw.split(",") if v.strip()]
            print(f"    Got {len(monitor_powers)} monitor values")
        else:
            monitor_powers = []
    except Exception:
        monitor_powers = []

    # 生成波长数组
    n = len(powers)
    wavelengths = np.linspace(START_WL, STOP_WL, n)
    powers_arr = np.array(powers)
    monitor_arr = np.array(monitor_powers) if monitor_powers else np.full(n, np.nan)

    # 保存 CSV
    print(f"\n    Saving to {CSV_FILE} ...")
    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["# Santec Scan Data"])
        writer.writerow([f"# Timestamp: {datetime.now(timezone.utc).isoformat()}"])
        writer.writerow([f"# Start: {START_WL}nm, Stop: {STOP_WL}nm, Step: {STEP}nm"])
        writer.writerow([f"# Speed: {SPEED}nm/s, Points: {n}"])
        writer.writerow(["wavelength_nm", "power_dbm", "monitor_dbm"])
        for i in range(n):
            mon_val = monitor_arr[i] if not np.isnan(monitor_arr[i]) else ""
            writer.writerow([f"{wavelengths[i]:.4f}", f"{powers_arr[i]:.6f}", mon_val])

    print(f"    Saved {n} data points")

    # 绘图
    print("\n    Plotting ...")
    import matplotlib

    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    ax1.plot(wavelengths, powers_arr, "b-", linewidth=0.5)
    ax1.set_ylabel("Power (dBm)")
    ax1.set_title(f"MPM Power — {START_WL}-{STOP_WL}nm, {n} points")
    ax1.grid(True, alpha=0.3)

    if not np.all(np.isnan(monitor_arr)):
        ax2.plot(wavelengths, monitor_arr, "r-", linewidth=0.5)
        ax2.set_ylabel("Monitor Power (dBm)")
        ax2.set_title("TSL Power Monitor")
    ax2.set_xlabel("Wavelength (nm)")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(CSV_FILE.replace(".csv", ".png"), dpi=150)
    print(f"    Plot saved to {CSV_FILE.replace('.csv', '.png')}")
    plt.show()
    print("    Done.")


if __name__ == "__main__":
    main()
