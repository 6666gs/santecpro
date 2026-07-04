#!/usr/bin/env python3
"""测试 TSL trigger standby + sweep mode：一次软触发走完全程。

验证假设：
  - WAV:SWE:MOD 1 (Continuous One-way) + TRIG:INP:STAN 1 (Trigger standby)
  - WAV:SWE 1 → TSL 进入 standby 等待触发
  - WAV:SWE:SOFT → 一次软触发，激光走完整个扫描范围
  - 同时 MPM 收到 TSL 的 TRIG:OUTP(step) 脉冲完成数据采集

用法:
    python examples/debug_trigger_sweep.py
"""

import time

import numpy as np
import requests

SERVER = "http://192.168.1.103:5000"

# 扫描参数
START_WL = 1550.0
STOP_WL = 1560.0
STEP = 0.01
SPEED = 2.0
POWER = 1.0
MPM_RANGE = 1


def api(path, data=None, timeout=30):
    resp = requests.post(f"{SERVER}{path}", json=data, timeout=timeout)
    result = resp.json()
    if "error" in result:
        print(f"    ERROR: {result['error']}")
        return None
    return result


def write(target, cmd):
    api(f"/api/{target}/command", {"command": cmd, "mode": "write"})


class FatalMPMError(Exception):
    """MPM 遇到 -221 (Setting conflict)，需要物理重启。"""

    pass


def check_mpm_fatal():
    """检查 MPM 是否有 -221 错误。如果有则抛出异常终止程序。"""
    err = query("mpm", "ERR?")
    if err and "-221" in err:
        raise FatalMPMError(
            f"MPM ERR={err} — Setting conflict, 必须物理重启 MPM 后再运行"
        )
    return err


def query(target, cmd):
    data = api(f"/api/{target}/command", {"command": cmd, "mode": "query"})
    if data and "response" in data:
        print(f"    {target} Q: {cmd:25s} -> {data['response']}")
        return data["response"]
    return None


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def main():
    section("Step 0: 连接仪器")
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

    # ---- 清理上次残留状态 ----
    section("Step 1: 清理残留状态 (关键!)")
    # 验证 MPM 状态
    write("mpm", "STOP")
    time.sleep(1)
    stat = query("mpm", "STAT?")
    err = query("mpm", "ERR?")
    print(f"    -> MPM STAT={stat}, ERR={err}")
    write("mpm", "STOP")
    time.sleep(1)
    check_mpm_fatal()  # 检查清理后是否仍有 -221
    # ---- 查询初始状态 ----
    section("Step 2: 查询初始状态")
    print("  --- TSL ---")
    query("tsl", "POW:STAT?")
    query("tsl", "POW:SHUT?")
    query("tsl", "WAV:SWE:MOD?")
    query("tsl", "TRIG:OUTP?")
    query("tsl", "TRIG:OUTP:STEP?")
    print("  --- MPM ---")
    query("mpm", "WMOD?")
    query("mpm", "WSET?")
    query("mpm", "SPE?")
    query("mpm", "LEV?")
    query("mpm", "TRIG?")
    query("mpm", "LOGN?")
    query("mpm", "UNIT?")
    query("mpm", "ERR?")

    # ---- 配置 TSL ----
    section("Step 3: 配置 TSL")
    write("tsl", f"POW:LEV {POWER:.2f}")
    print(f"    Power -> {POWER} dBm")

    write("tsl", "WAV:SWE:MOD 1")
    print("    Sweep mode -> 1 (Continuous One-way)")

    write("tsl", f"WAV:SWE:STAR {START_WL:.4f}")
    write("tsl", f"WAV:SWE:STOP {STOP_WL:.4f}")
    write("tsl", f"WAV:SWE:STEP {STEP:.4f}")
    write("tsl", f"WAV:SWE:SPE {SPEED:.1f}")
    write("tsl", f"TRIG:OUTP:STEP {STEP:.4f}")  # 每步输出一个 trigger，不是每 4 步
    expected_points = int((STOP_WL - START_WL) / STEP) + 1
    expected_time = (STOP_WL - START_WL) / SPEED
    print(f"    Sweep: {START_WL}->{STOP_WL}nm, step={STEP}nm, speed={SPEED}nm/s")
    print(f"    Expected: {expected_points} points, ~{expected_time:.1f}s")

    write("tsl", "TRIG:OUTP 3")
    print("    Trigger output -> 3 (Step)")

    # ---- 开启激光 ----
    section("Step 4: 开启激光")
    write("tsl", "POW:SHUT 0")
    time.sleep(0.2)
    write("tsl", "POW:STAT 1")
    time.sleep(1)
    laser = query("tsl", "POW:STAT?")
    shutter = query("tsl", "POW:SHUT?")
    if not (laser and laser.strip().endswith("1")):
        print(f"    WARNING: Laser status unclear, got '{laser}' (continuing anyway)")
    if not (shutter and shutter.strip().endswith("0")):
        print(
            f"    WARNING: Shutter status unclear, got '{shutter}' (continuing anyway)"
        )

    # # ---- 配置 MPM (严格按官方序列) ----
    # 官方序列: WMOD → WSET → SPE → LEV → TRIG → MEAS
    section("Step 5: 配置 MPM (官方序列)")
    write("mpm", "WMOD SWEEP1")  # 1. 测量模式
    write("mpm", f"WSET {START_WL:.3f},{STOP_WL:.3f},{STEP:.3f}")  # 2. 波长范围
    write("mpm", f"SPE {SPEED:.3f}")  # 3. 扫描速度
    write("mpm", f"LEV {MPM_RANGE}")  # 4. TIA Gain Level
    write("mpm", "TRIG 1")  # 5. 外部触发
    print(f"    WMOD SWEEP1, WSET {START_WL},{STOP_WL},{STEP}, SPE {SPEED}")
    print(f"    LEV {MPM_RANGE}, TRIG 1 (External)")
    check_mpm_fatal()  # MPM 配置后检查 -221
    query("mpm", "ERR?")
    logn = query("mpm", "LOGN?")
    # if logn:
    #     n = int(logn)
    #     print(f"    -> MPM expects {n} data points (auto from WSET)")
    #     assert n == expected_points, f"LOGN mismatch: {n} vs expected {expected_points}"

    # ---- 启动 MPM 测量 ----
    section("Step 6: 启动 MPM 测量 (MEAS)")

    # 关键：MEAS 前 STAT 必须是 -1（stopped），否则会丢失前几个触发脉冲
    pre_stat = query("mpm", "STAT?")
    if pre_stat and not pre_stat.startswith("-1"):
        print(f"\n    ABORT: MPM STAT={pre_stat}, expected -1 (stopped)")
        print(f"    MPM 未处于干净状态，扫描会丢失数据点")
        print(f"    请物理重启 MPM-210 后重新运行")
        return

    write("mpm", "MEAS")
    time.sleep(1.0)
    stat = query("mpm", "STAT?")
    query("mpm", "ERR?")
    check_mpm_fatal()  # MEAS 后检查 -221

    # # ---- 设置 TSL trigger standby ----
    section("Step 8: 设置 TSL trigger standby (TRIG:INP:STAN 1)")
    write("tsl", "TRIG:INP:STAN 1")
    time.sleep(0.3)
    stan = query("tsl", "TRIG:INP:STAN?")
    if not (stan and stan.strip().endswith("1")):
        print(
            f"    WARNING: Trigger standby expected 1, got '{stan}' (continuing anyway)"
        )
    print("    -> Trigger standby ON, confirmed")

    # ---- 启动 TSL sweep (进入 standby) ----
    section("Step 9: WAV:SWE 1 (TSL 进入 trigger standby 状态)")
    write("tsl", "WAV:SWE 1")
    time.sleep(0.5)
    sweep_status = query("tsl", "WAV:SWE?")
    print(f"    -> WAV:SWE={sweep_status} (should be 3 = Trigger standby)")

    # ---- 发送软触发 ----
    section("Step 10: 发送软触发 (WAV:SWE:SOFT) — 一次触发走完全程!")
    print("    Sending soft trigger...")
    time.sleep(1.0)  # 等待一会，确保 TSL 已经完全进入 standby 状态
    write("tsl", "WAV:SWE:SOFT")
    time.sleep(0.3)
    sweep_status = query("tsl", "WAV:SWE?")
    print(f"    -> WAV:SWE={sweep_status} (should be 1=Running or 4=Returning)")

    # ---- 轮询完成 ----
    section("Step 11: 轮询 MPM + TSL 状态")
    start = time.time()
    done = False
    for i in range(60):
        time.sleep(1)
        stat = query("mpm", "STAT?")
        sweep = query("tsl", "WAV:SWE?")
        elapsed = time.time() - start
        print(f"    [{elapsed:.0f}s] MPM STAT={stat}, TSL WAV:SWE={sweep}")

        if stat and stat.startswith("1"):
            count = stat.split(",")[1] if "," in stat else "?"
            print(f"\n    SUCCESS! MPM measurement COMPLETE! {count} data points")
            done = True
            break
        if sweep and sweep.strip() == "0" and elapsed > 3:
            print(f"\n    TSL sweep finished, waiting for MPM...")
            for _ in range(5):
                time.sleep(1)
                stat = query("mpm", "STAT?")
                if stat and stat.startswith("1"):
                    count = stat.split(",")[1] if "," in stat else "?"
                    print(f"    SUCCESS! MPM measurement COMPLETE! {count} data points")
                    done = True
                    break
            break
    if not done:
        print("\n    FAILED! MPM never completed")

    # if done:
    #     write("mpm", "STOP")
    #     time.sleep(0.5)
    #     check_mpm_fatal()  # LOGG? 前检查 -221
    #     raw_data = query("mpm", "LOGG? 0,0")
    #     if raw_data:
    #         print(f"    Got LOGG? data: {len(raw_data)} chars")
    #     else:
    #         print("    Failed to get LOGG? data")

    # ---- 读取数据并绘图 ----
    if done:
        section("Step 12: STOP → LOGG? → CSV → Plot")

        # 关键：先 STOP 再读数据！
        # 如果先 LOGG? 再 STOP，MPM 会卡在 STAT=0 无法做第二次扫描
        print("    Phase 1: STOP before reading data...")
        write("mpm", "STOP")
        time.sleep(0.5)
        stat = query("mpm", "STAT?")

        print("    Phase 2: Read LOGG? data...")
        powers = []
        active_channel = 1  # 要读取的通道号 (1-4)
        try:
            resp = requests.post(
                f"{SERVER}/api/mpm/data",
                json={"module": 0, "channel": active_channel},
                timeout=30,
            )
            data = resp.json()
            if "error" in data:
                print(f"    ERROR: {data['error']}")
            else:
                raw_powers = data.get("powers", [])
                n_raw = len(raw_powers)
                print(f"    Got {n_raw} power values from LOGG?")

                if n_raw == expected_points:
                    # 单通道数据，直接使用
                    powers = raw_powers
                elif n_raw == expected_points * 4:
                    # 4 通道交错数据，提取 active_channel
                    powers = raw_powers[active_channel - 1 :: 4]
                    print(
                        f"    De-interleaved 4 channels, using channel {active_channel}"
                    )
                else:
                    print(
                        f"    WARNING: unexpected count {n_raw} (expected {expected_points})"
                    )
                    powers = raw_powers

                print(
                    f"    Final: {len(powers)} points, range [{min(powers):.2f}, {max(powers):.2f}] dBm"
                )
        except Exception as e:
            print(f"    ERROR reading LOGG?: {e}")

        # LOGG? 后再次 STOP
        print("    Phase 3: STOP after LOGG?...")
        write("mpm", "STOP")
        time.sleep(0.5)
        stat = query("mpm", "STAT?")
        print(f"    -> MPM STAT after cleanup: {stat}")

        if powers:
            n = len(powers)

            # 读取 TSL power monitor
            mon_resp = api(
                "/api/tsl/command", {"command": ":READ:DAT?", "mode": "query"}
            )
            monitor_powers = []
            if mon_resp:
                mon_raw = mon_resp.get("response", "")
                monitor_powers = [float(v) for v in mon_raw.split(",") if v.strip()]
                print(f"    Got {len(monitor_powers)} monitor values from TSL")

            # 生成波长数组
            wavelengths = np.linspace(START_WL, STOP_WL, n)
            powers_arr = np.array(powers)
            # monitor 值数量可能不匹配，统一用 nan 填充
            if len(monitor_powers) == n:
                monitor_arr = np.array(monitor_powers)
            else:
                monitor_arr = np.full(n, np.nan)
                if monitor_powers:
                    print(
                        f"    WARNING: monitor has {len(monitor_powers)} values, expected {n}"
                    )

            # 保存 CSV
            import csv
            from datetime import datetime, timezone

            csv_file = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            with open(csv_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["# Santec Scan Data"])
                writer.writerow(
                    [f"# Timestamp: {datetime.now(timezone.utc).isoformat()}"]
                )
                writer.writerow(
                    [
                        f"# Range: {START_WL}-{STOP_WL}nm, Step: {STEP}nm, Speed: {SPEED}nm/s"
                    ]
                )
                writer.writerow(["wavelength_nm", "power_dbm", "monitor_dbm"])
                for i in range(n):
                    mon_val = (
                        f"{monitor_arr[i]:.6f}" if not np.isnan(monitor_arr[i]) else ""
                    )
                    writer.writerow(
                        [f"{wavelengths[i]:.4f}", f"{powers_arr[i]:.6f}", mon_val]
                    )
            print(f"    Saved to {csv_file}")

    #         # 绘图
    #         import matplotlib

    #         matplotlib.use("TkAgg")
    #         import matplotlib.pyplot as plt

    #         fig, ax = plt.subplots(figsize=(12, 5))
    #         ax.plot(wavelengths, powers_arr, "b-", linewidth=0.5)
    #         ax.set_xlabel("Wavelength (nm)")
    #         ax.set_ylabel("Power (dBm)")
    #         ax.set_title(
    #             f"Santec Scan: {START_WL}-{STOP_WL}nm, {n} points, Range={MPM_RANGE}"
    #         )
    #         ax.grid(True, alpha=0.3)
    #         plt.tight_layout()
    #         png_file = csv_file.replace(".csv", ".png")
    #         plt.savefig(png_file, dpi=150)
    #         print(f"    Plot saved to {png_file}")
    #         plt.show()

    # ---- 清理 ----
    section("清理")
    write("mpm", "STOP")
    write("tsl", "WAV:SWE 0")
    write("tsl", "TRIG:INP:STAN 0")
    print("    Done.")


if __name__ == "__main__":
    try:
        main()
        # query("mpm", "IDIS?")
    except FatalMPMError as e:
        print(f"\n{'='*60}")
        print(f"  FATAL: {e}")
        print(f"  请物理重启 MPM-210 后重新运行脚本")
        print(f"{'='*60}")
