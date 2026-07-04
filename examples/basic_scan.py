#!/usr/bin/env python3
"""远程扫描示例 — Mac 端通过 HTTP 控制 Windows 上的 Santec 设备。

用法:
    python examples/basic_scan.py

前提条件:
    - Windows 电脑运行 server.py，连接 TSL-550 和 MPM-210
    - Mac 和 Windows 在同一局域网
    - pip install requests numpy matplotlib
"""

import logging
from santecpro import RemoteScanner

# 开启日志
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")


def main():
    # Windows 服务器地址（修改为实际 IP）
    SERVER_URL = "http://192.168.1.103:5000"

    scanner = RemoteScanner(SERVER_URL)

    # 查询服务器状态
    print("Server status:", scanner.status())

    # 连接仪器
    print("\nConnecting to instruments...")
    scanner.connect(
        tsl_address="GPIB3::1::INSTR",
        mpm_address="GPIB0::16::INSTR",
    )

    # 开启激光器
    scanner.laser_on()

    # 配置扫描参数
    scanner.configure(
        start_wl=1550.0,
        stop_wl=1560.0,
        step=0.01,
        speed=2.0,
        power=1.0,
        sweep_mode=1,  # Continuous One-way (see tsl.SWEEP_MODE_CONT_ONE_WAY)
        ranges=[1],
    )

    # 执行单次扫描
    print("\nStarting scan...")
    result = scanner.run_single_scan(
        mpm_range=1,
        plot=True,
        save_csv="scan_result_raw.csv",
    )
    print(f"Scan complete: {len(result.wavelengths)} data points")
    print(
        f"Wavelength range: {result.wavelengths[0]:.3f} - {result.wavelengths[-1]:.3f} nm"
    )
    print(f"Power range: {result.powers.min():.2f} - {result.powers.max():.2f} dBm")

    # 关闭激光器
    scanner.laser_off()

    # 断开连接
    scanner.disconnect()
    print("\nDone.")


if __name__ == "__main__":
    main()
