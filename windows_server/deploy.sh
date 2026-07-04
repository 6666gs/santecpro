#!/usr/bin/env python3
"""将 santecpro 核心库复制到 windows_server 目录，方便整体拷贝到 Windows 电脑。

用法:
    python windows_server/pack_for_windows.py

生成的 windows_server/ 目录可以直接打包拷贝到 Windows 电脑。
"""

import shutil
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "santecpro")
DST_DIR = os.path.join(BASE_DIR, "windows_server", "santecpro")

# 需要复制的文件（Windows 端只需要核心驱动和扫描器）
NEEDED_FILES = [
    "__init__.py",
    "exceptions.py",
    "exporter.py",
    "remote.py",
    "reference.py",
    "scanner.py",
    "server_control.py",
    "sweep_rules.py",
    "ui_app.py",
    "ui_controller.py",
    "instruments/__init__.py",
    "instruments/base.py",
    "instruments/tsl.py",
    "instruments/mpm.py",
]

# 不需要的文件（Mac 端专用或测试用）
SKIP_FILES = {
    "plotter.py",
}


def main():
    print(f"Copying santecpro to {DST_DIR}...")

    # 清理旧目录
    if os.path.exists(DST_DIR):
        shutil.rmtree(DST_DIR)

    # 创建目录结构
    os.makedirs(os.path.join(DST_DIR, "instruments"), exist_ok=True)

    # 复制文件
    for rel_path in NEEDED_FILES:
        src = os.path.join(SRC_DIR, rel_path)
        dst = os.path.join(DST_DIR, rel_path)
        shutil.copy2(src, dst)
        print(f"  {rel_path}")

    # 生成 Windows 端专用的轻量 __init__.py。
    # DLL 诊断脚本只需要导入 santecpro.sweep_rules；这里避免包初始化时
    # 立刻导入 pyvisa/Qt 等可选依赖。
    init_content = '''"""Santecpro — Cross-platform Python driver for Santec TSL-550 and MPM-210."""

__version__ = "1.0.0"

__all__ = ["__version__"]
'''
    init_path = os.path.join(DST_DIR, "__init__.py")
    with open(init_path, "w") as f:
        f.write(init_content)
    print(f"  __init__.py (Windows version, no remote import)")

    # 验证
    print(f"\nDone! windows_server/ 目录内容:")
    for root, dirs, files in os.walk(os.path.join(BASE_DIR, "windows_server")):
        # 跳过 __pycache__
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        level = root.replace(os.path.join(BASE_DIR, "windows_server"), "").count(os.sep)
        indent = "  " * level
        folder = os.path.basename(root)
        print(f"{indent}{folder}/")
        for f in files:
            print(f"{indent}  {f}")

    print(f"\n将 windows_server/ 文件夹整体拷贝到 Windows 电脑后:")
    print(f"  1. pip install -r requirements.txt")
    print(f"  2. python server.py --tsl GPIB3::1::INSTR --mpm GPIB0::16::INSTR")


if __name__ == "__main__":
    main()
