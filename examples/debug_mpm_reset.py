#!/usr/bin/env python3
"""测试 MPM 重置方法：找到正确的清理序列。

目标：让 MPM 从 "Program currently running" 状态恢复到可接受 MEAS 的状态。

用法:
    python examples/debug_mpm_reset.py
"""

import time
import requests

SERVER = "http://192.168.1.103:5000"


def api(path, data=None, timeout=30):
    resp = requests.post(f"{SERVER}{path}", json=data, timeout=timeout)
    result = resp.json()
    if "error" in result:
        print(f"    ERROR: {result['error']}")
        return None
    return result


def write(target, cmd):
    api(f"/api/{target}/command", {"command": cmd, "mode": "write"})


def query(target, cmd):
    data = api(f"/api/{target}/command", {"command": cmd, "mode": "query"})
    if data and "response" in data:
        print(f"    {target} Q: {cmd:25s} -> {data['response']}")
        return data["response"]
    return None


def drain_errors(target="mpm", max_reads=30):
    """读取 ERR? 直到返回 0 或队列为空。"""
    print(f"    Draining {target} error queue:")
    count = 0
    for _ in range(max_reads):
        err = query(target, "ERR?")
        if not err:
            break
        count += 1
        if err.strip().startswith("0"):
            print(f"    -> Cleared {count} errors, queue now empty")
            return count
    print(f"    -> Drained {count} errors, queue may still have entries")
    return count


def main():
    print("=" * 60)
    print("  MPM Reset Test")
    print("=" * 60)

    # 连接
    result = api("/api/connect", {
        "tsl_address": "GPIB3::1::INSTR",
        "mpm_address": "GPIB0::16::INSTR",
    })
    if not result:
        return

    # 查看当前状态
    print("\n--- Current MPM state ---")
    query("mpm", "STAT?")
    query("mpm", "ERR?")
    query("mpm", "WMOD?")
    query("mpm", "WSET?")

    # ============================================================
    # Test 1: STOP only, then MEAS
    # ============================================================
    print("\n" + "=" * 60)
    print("  Test 1: STOP -> drain ERR -> MEAS")
    print("=" * 60)

    write("mpm", "STOP")
    time.sleep(1)
    drain_errors()
    query("mpm", "STAT?")
    query("mpm", "ERR?")

    print("\n    Sending MEAS...")
    write("mpm", "MEAS")
    time.sleep(1)
    stat = query("mpm", "STAT?")
    err = query("mpm", "ERR?")
    if stat and not stat.startswith("-1"):
        print("    >>> TEST 1 PASSED: MEAS accepted!")
    else:
        print("    >>> TEST 1 FAILED: MEAS rejected")

    # Cleanup
    write("mpm", "STOP")
    drain_errors()

    # ============================================================
    # Test 2: STOP -> WMOD NORMAL -> drain ERR -> WMOD SWEEP1 -> reconfig -> MEAS
    # ============================================================
    print("\n" + "=" * 60)
    print("  Test 2: STOP -> WMOD NORMAL -> drain ERR -> reconfig -> MEAS")
    print("=" * 60)

    write("mpm", "STOP")
    time.sleep(0.5)
    write("mpm", "WMOD NORMAL")
    time.sleep(0.5)
    drain_errors()

    # 重新配置
    write("mpm", "WMOD SWEEP1")
    write("mpm", "WSET 1550.000,1560.000,0.010")
    write("mpm", "SPE 2.000")
    write("mpm", "LEV 1")
    write("mpm", "TRIG 1")
    time.sleep(0.5)
    drain_errors()

    print("\n    Sending MEAS...")
    write("mpm", "MEAS")
    time.sleep(1)
    stat = query("mpm", "STAT?")
    err = query("mpm", "ERR?")
    if stat and not stat.startswith("-1"):
        print("    >>> TEST 2 PASSED: MEAS accepted!")
    else:
        print("    >>> TEST 2 FAILED: MEAS rejected")

    # Cleanup
    write("mpm", "STOP")
    drain_errors()

    # ============================================================
    # Test 3: No reconfig, just STOP -> drain ERR -> MEAS
    # (settings should still be correct from Test 2)
    # ============================================================
    print("\n" + "=" * 60)
    print("  Test 3: No reconfig, just STOP -> drain ERR -> MEAS")
    print("=" * 60)

    write("mpm", "STOP")
    time.sleep(1)
    drain_errors()
    query("mpm", "STAT?")

    print("\n    Sending MEAS (without reconfig)...")
    write("mpm", "MEAS")
    time.sleep(1)
    stat = query("mpm", "STAT?")
    err = query("mpm", "ERR?")
    if stat and not stat.startswith("-1"):
        print("    >>> TEST 3 PASSED: MEAS accepted!")
    else:
        print("    >>> TEST 3 FAILED: MEAS rejected")

    # Cleanup
    write("mpm", "STOP")
    drain_errors()

    # Final state
    print("\n--- Final MPM state ---")
    query("mpm", "STAT?")
    query("mpm", "ERR?")
    query("mpm", "WMOD?")
    query("mpm", "LOGN?")

    write("mpm", "STOP")


if __name__ == "__main__":
    main()
