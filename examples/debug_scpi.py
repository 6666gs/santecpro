#!/usr/bin/env python3
"""SCPI 命令验证工具 — 验证修正后的 MPM-210 和 TSL-550 命令。

用法:
    python examples/debug_scpi.py
"""

import requests

SERVER = "http://192.168.1.103:5000"


def tsl_query(cmd):
    resp = requests.post(f"{SERVER}/api/tsl/command", json={"command": cmd, "mode": "query"}, timeout=10)
    data = resp.json()
    tag = "OK" if "response" in data else "ERR"
    print(f"  TSL Q: {cmd:30s} → {data.get('response', data.get('error', '?'))}  [{tag}]")
    return data


def tsl_write(cmd):
    resp = requests.post(f"{SERVER}/api/tsl/command", json={"command": cmd, "mode": "write"}, timeout=10)
    data = resp.json()
    tag = "OK" if "error" not in data else "ERR"
    print(f"  TSL W: {cmd:30s} → {tag}")
    return data


def mpm_query(cmd):
    try:
        resp = requests.post(f"{SERVER}/api/mpm/command", json={"command": cmd, "mode": "query"}, timeout=10)
        data = resp.json()
        tag = "OK" if "response" in data else "ERR"
        print(f"  MPM Q: {cmd:30s} → {data.get('response', data.get('error', '?'))}  [{tag}]")
        return data
    except Exception as e:
        print(f"  MPM Q: {cmd:30s} → TIMEOUT: {e}  [ERR]")
        return {"error": str(e)}


def mpm_write(cmd):
    try:
        resp = requests.post(f"{SERVER}/api/mpm/command", json={"command": cmd, "mode": "write"}, timeout=10)
        data = resp.json()
        tag = "OK" if "error" not in data else "ERR"
        print(f"  MPM W: {cmd:30s} → {tag}")
        return data
    except Exception as e:
        print(f"  MPM W: {cmd:30s} → TIMEOUT: {e}  [ERR]")
        return {"error": str(e)}


def connect(tsl_address="GPIB3::1::INSTR", mpm_address="GPIB0::16::INSTR"):
    resp = requests.post(f"{SERVER}/api/connect", json={
        "tsl_address": tsl_address,
        "mpm_address": mpm_address,
    }, timeout=30)
    data = resp.json()
    if "error" in data:
        print(f"  CONNECT → ERROR: {data['error']}")
        return False
    print(f"  CONNECT → OK  TSL={data.get('tsl_idn', '?')}  MPM={data.get('mpm_idn', '?')}")
    return True


def main():
    print("=" * 60)
    print("验证修正后的 SCPI 命令 (基于官方手册)")
    print("=" * 60)

    # 0. 连接仪器
    print("\n--- 0. 连接仪器 ---")
    if not connect():
        print("连接失败，退出。")
        return

    # 1. 设备识别
    print("\n--- 1. 设备识别 ---")
    mpm_query("*IDN?")
    tsl_query("*IDN?")

    # 2. MPM-210 原生命令 (非 SCPI)
    print("\n--- 2. MPM-210 原生命令 ---")
    mpm_query("WAV?")
    mpm_query("LEV?")
    mpm_query("AUTO?")
    mpm_query("AVG?")
    mpm_query("UNIT?")
    mpm_query("WMOD?")
    mpm_query("TRIG?")
    mpm_query("LOGN?")
    mpm_query("STAT?")
    mpm_query("READ? 0")

    # 3. TSL-550 SCPI Command Set 1
    print("\n--- 3. TSL-550 SCPI 命令 ---")
    tsl_query("POW:STAT?")
    tsl_query("POW:SHUT?")
    tsl_query("POW:LEV?")
    tsl_query("WAV?")
    tsl_query("WAV:SWE?")
    tsl_query("WAV:SWE:MOD?")
    tsl_query("WAV:SWE:SPE?")
    tsl_query("TRIG:OUTP?")
    tsl_query(":READ:POIN?")

    # 4. 快速功能测试 (不改变仪器状态)
    print("\n--- 4. 功能验证 (只读) ---")
    mpm_query("WSET?")
    mpm_query("SPE?")

    print("\n" + "=" * 60)
    print("验证完成。所有命令应返回 OK + 数值。")
    print("如有 ERR 或 TIMEOUT，请将输出发给我排查。")
    print("=" * 60)


if __name__ == "__main__":
    main()
