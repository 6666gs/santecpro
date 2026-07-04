#!/usr/bin/env python3
"""逐步诊断扫描流程 — 定位卡住的原因。

用法:
    python examples/debug_scan.py
"""

import time
import requests

SERVER = "http://192.168.1.103:5000"


def api(path, data=None, timeout=30):
    resp = requests.post(f"{SERVER}{path}", json=data, timeout=timeout)
    result = resp.json()
    if "error" in result:
        print(f"    ❌ ERROR: {result['error']}")
        return None
    return result


def query_instrument(target, cmd):
    """向仪器发送查询并打印结果。"""
    data = api(f"/api/{target}/command", {"command": cmd, "mode": "query"})
    if data and "response" in data:
        print(f"    {target} Q: {cmd:25s} → {data['response']}")
        return data["response"]
    return None


def main():
    print("=" * 60)
    print("逐步扫描诊断")
    print("=" * 60)

    # === Step 0: 连接 ===
    print("\n[Step 0] 连接仪器...")
    result = api("/api/connect", {
        "tsl_address": "GPIB3::1::INSTR",
        "mpm_address": "GPIB0::16::INSTR",
    })
    if not result:
        return
    print(f"    TSL: {result.get('tsl_idn', '?')}")
    print(f"    MPM: {result.get('mpm_idn', '?')}")

    # === Step 1: 查询初始状态 ===
    print("\n[Step 1] 查询仪器初始状态...")
    query_instrument("tsl", "POW:STAT?")
    query_instrument("tsl", "POW:SHUT?")
    query_instrument("tsl", "WAV?")
    query_instrument("tsl", "WAV:SWE?")
    query_instrument("tsl", "TRIG:OUTP?")
    query_instrument("tsl", "TRIG:OUTP:STEP?")
    query_instrument("tsl", "WAV:SWE:MOD?")
    query_instrument("tsl", "WAV:SWE:SPE?")
    query_instrument("tsl", "TRIG:INP:STAN?")
    query_instrument("mpm", "WMOD?")
    query_instrument("mpm", "WSET?")
    query_instrument("mpm", "SPE?")
    query_instrument("mpm", "LEV?")
    query_instrument("mpm", "TRIG?")
    query_instrument("mpm", "LOGN?")
    query_instrument("mpm", "STAT?")
    query_instrument("mpm", "UNIT?")

    # === Step 2: 配置 TSL ===
    print("\n[Step 2] 配置 TSL...")
    api("/api/tsl/command", {"command": "POW:LEV 1.00", "mode": "write"})
    print("    TSL power → 1.00 dBm")
    api("/api/tsl/command", {"command": "WAV:SWE:MOD 1", "mode": "write"})
    print("    TSL sweep mode → 1 (Continuous One-way)")
    api("/api/tsl/command", {"command": "WAV:SWE:STAR 1550.0000", "mode": "write"})
    api("/api/tsl/command", {"command": "WAV:SWE:STOP 1560.0000", "mode": "write"})
    api("/api/tsl/command", {"command": "WAV:SWE:STEP 0.0100", "mode": "write"})
    api("/api/tsl/command", {"command": "WAV:SWE:SPE 2.0", "mode": "write"})
    print("    TSL sweep: 1550→1560nm, step=0.01nm, speed=2nm/s")
    api("/api/tsl/command", {"command": "TRIG:OUTP 3", "mode": "write"})
    print("    TSL trigger output → Step (3)")
    api("/api/tsl/command", {"command": "TRIG:OUTP:STEP 0.0100", "mode": "write"})
    print("    TSL trigger step width → 0.01nm")

    # 验证 TSL 配置
    print("    验证 TSL 配置:")
    query_instrument("tsl", "TRIG:OUTP?")
    query_instrument("tsl", "TRIG:OUTP:STEP?")

    # === Step 3: 开启激光 ===
    print("\n[Step 3] 开启激光和快门...")
    api("/api/tsl/command", {"command": "POW:SHUT 0", "mode": "write"})
    api("/api/tsl/command", {"command": "POW:STAT 1", "mode": "write"})
    time.sleep(1)
    query_instrument("tsl", "POW:STAT?")
    query_instrument("tsl", "POW:SHUT?")

    # === Step 4: 配置 MPM ===
    print("\n[Step 4] 配置 MPM...")
    api("/api/mpm/command", {"command": "UNIT 0", "mode": "write"})     # dBm
    print("    MPM unit → dBm")
    api("/api/mpm/command", {"command": "AUTO 0", "mode": "write"})     # Manual range
    print("    MPM range mode → Manual")
    api("/api/mpm/command", {"command": "WMOD SWEEP1", "mode": "write"})
    print("    MPM mode → SWEEP1")
    api("/api/mpm/command", {"command": "WSET 1550.000,1560.000,0.010", "mode": "write"})
    print("    MPM WSET 1550,1560,0.01")
    api("/api/mpm/command", {"command": "SPE 2.000", "mode": "write"})
    print("    MPM speed → 2nm/s")

    # 验证 MPM 自动计算的 LOGN
    print("    验证 MPM LOGN (应由 WSET 自动计算):")
    logn = query_instrument("mpm", "LOGN?")
    if logn:
        n = int(logn)
        print(f"    → MPM 期待 {n} 个数据点")

    # === Step 5: 设置 range + trigger ===
    print("\n[Step 5] 设置 MPM range 和 trigger...")
    api("/api/mpm/command", {"command": "LEV 1", "mode": "write"})
    print("    MPM range → 1")
    api("/api/mpm/command", {"command": "TRIG 1", "mode": "write"})
    print("    MPM trigger → External (1)")
    query_instrument("mpm", "TRIG?")
    query_instrument("mpm", "STAT?")

    # === Step 6: 开始 MPM 测量 ===
    print("\n[Step 6] 启动 MPM 测量 (MEAS)...")
    api("/api/mpm/command", {"command": "MEAS", "mode": "write"})
    time.sleep(0.5)
    stat = query_instrument("mpm", "STAT?")
    print(f"    → MPM 应处于 'measuring' 状态 (status=0)")

    # === Step 7: 设置 TSL trigger standby ===
    print("\n[Step 7] 设置 TSL trigger standby...")
    api("/api/tsl/command", {"command": "TRIG:INP:STAN 1", "mode": "write"})
    query_instrument("tsl", "TRIG:INP:STAN?")

    # === Step 8: 启动 TSL 扫描 ===
    print("\n[Step 8] 启动 TSL 扫描 (WAV:SWE 1)...")
    api("/api/tsl/command", {"command": "WAV:SWE 1", "mode": "write"})
    time.sleep(0.3)
    query_instrument("tsl", "WAV:SWE?")
    print("    → 应为 3 (Trigger standby)")

    # === Step 9: 软触发开始 ===
    print("\n[Step 9] 发送软触发 (WAV:SWE:SOFT)...")
    api("/api/tsl/command", {"command": "WAV:SWE:SOFT", "mode": "write"})
    time.sleep(1)
    query_instrument("tsl", "WAV:SWE?")
    print("    → 应为 1 (Running) 或 4 (Returning)")

    # === Step 10: 轮询 MPM 状态 ===
    print("\n[Step 10] 轮询 MPM STAT? (每 2 秒，最多 60 秒)...")
    start = time.time()
    for i in range(30):
        time.sleep(2)
        stat = query_instrument("mpm", "STAT?")
        sweep = query_instrument("tsl", "WAV:SWE?")
        elapsed = time.time() - start
        print(f"    [{elapsed:.0f}s] MPM STAT={stat}, TSL sweep={sweep}")

        if stat and stat.startswith("1"):
            print(f"\n    ✅ MPM 测量完成!")
            break
        if sweep and sweep.startswith("0"):
            print(f"\n    ⚠️ TSL 扫描已结束，但 MPM 还没完成")
    else:
        print("\n    ❌ 超时！MPM 始终未完成")

    # 最终状态
    print("\n[最终状态]")
    query_instrument("mpm", "STAT?")
    query_instrument("mpm", "LOGN?")
    query_instrument("tsl", "WAV:SWE?")
    query_instrument("tsl", "TRIG:OUTP?")
    query_instrument("tsl", "TRIG:OUTP:STEP?")

    # 清理
    print("\n[清理] 停止测量、关闭激光...")
    api("/api/mpm/command", {"command": "STOP", "mode": "write"})
    api("/api/tsl/command", {"command": "WAV:SWE 0", "mode": "write"})
    api("/api/tsl/command", {"command": "POW:SHUT 1", "mode": "write"})
    api("/api/tsl/command", {"command": "POW:STAT 0", "mode": "write"})


if __name__ == "__main__":
    main()
