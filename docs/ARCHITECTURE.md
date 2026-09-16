# santec 扫谱系统 — 架构总览

本文讲清楚系统为什么分两台电脑、数据怎么流、两端各放什么。**逐步部署与操作**见各文件夹指南:
[windows-server/README.md](../windows-server/README.md) · [remote-client/README.md](../remote-client/README.md)。

---

## 1. 为什么要两台电脑

真正驱动扫描的是 Santec 的 .NET DLL(`STSProcess.dll` + `Santec.Instrument.dll`),只能在 Windows 上通过 `pythonnet` 加载。于是:

- **Windows 电脑(服务端)**:物理连接仪器(GPIB)、加载 DLL、执行扫描,对外暴露 HTTP 接口。
- **Mac / 任意电脑(控制端)**:通过网络远程下发指令、取回数据、画图、算 IL、存 CSV。**不碰仪器、DLL、GPIB。**

## 2. 数据流与两条通道

```
┌───────────────────────────────────┐        ┌──────────────────────────────────────────┐
│ 控制端  remote-client/  (Mac)       │        │ Windows 电脑  windows-server/               │
│                                     │        │                                            │
│  run_ui.py ─ PyQt5 界面             │        │  server.py         Flask  0.0.0.0:5000      │
│  santecpro/remote.py ─ RemoteScanner│  HTTP  │  santec_dll_backend/  ◀ 真正扫描 (pythonnet)│
│  santecpro/results.py ─ IL/合并      │ ─────▶ │  stsprocess_api.py   请求 ↔ DLL 适配         │
│  exporter/plotter ─ CSV/画图         │ :5000  │  santecpro/          SCPI 备用驱动子集        │
│  config.py ─ SERVER_URL 等          │        │  vendor/santec_dll/  *.dll(已随仓库提供)      │
│  server_control / remote_sts_scan ──│  SSH   │  config.py           HOST/PORT/GPIB 地址     │
│                                     │ ─────▶ │  diagnostics/        诊断脚本                 │
└───────────────────────────────────┘        └────────────────────┬───────────────────────┘
                                                                   │ GPIB
                                              ┌────────────────────┴─────────────────────┐
                                              │ TSL-550  GPIB3::1  ·  MPM-210  GPIB0::16    │
                                              └───────────────────────────────────────────┘
```

- **HTTP(主通道)**:界面 / `RemoteScanner` → `POST /api/scan/stsprocess` → Flask → DLL。日常扫描走这条。
- **SSH(辅通道)**:`server_control.py` 远程启动 `server.py`;`remote_sts_scan.py` 远程直接跑 `diagnostics/diagnose_stsprocess_scan.py`。

## 3. 唯一必须对齐的配置

控制端 `config.py` 的 **`SERVER_URL` 的 IP:端口** 必须等于 Windows 端 `server.py` 的实际 IP 和监听端口。其余(GPIB 地址、扫描参数)可在界面里改并随请求下发。

各端配置都集中在自己的 `config.py`,且每项都能用环境变量覆盖(换环境时改一处即可)。

## 4. 共享代码与防漂移

两个文件夹各自自包含。少量两端都要的小模块(`exceptions.py`、`sweep_rules.py`)在两侧各存一份;以 `remote-client/santecpro/` 为源,用根目录 [`sync_shared.py`](../sync_shared.py) 同步(`--check` 校验一致)。

`exporter.py` 两侧也各有一份,仅类型注解导入路径不同(客户端 `results`,服务端 `scanner`),客户端版本现已按官方样本列结构扩展为多通道 Raw/Loss 导出；服务端备用 SCPI 导出保留旧格式。

## 5. 本地直连模式(仅 Windows 端保留)

`windows-server/santecpro/`(`instruments/` + `Scanner`)是一套 pyvisa 直连仪器的 SCPI 驱动,作为 DLL 路径之外的**备用/调试**手段。控制端已移除本地模式(纯遥控)。

> 注意:设计上 MPM logging 的若干 SCPI 命令尚未与官方手册完全核对,**生产扫描以 DLL 路径(`/api/scan/stsprocess`)为准**。

## 6. 目录总览

```
santecpro/
├── windows-server/     → 拷到 Windows 电脑(见其 README)
├── remote-client/      → 拷到控制电脑(见其 README)
├── docs/ARCHITECTURE.md  本文
├── sync_shared.py      共享小模块同步
└── README.md           顶层导航
```

## 7. 关键接口(服务端)

| 方法 & 路径 | 用途 |
|---|---|
| `GET  /api/status` | 健康检查 + 仪器状态 |
| `POST /api/scan/stsprocess` | 主扫描接口(DLL 路径) |
| `GET  /api/scan/state` | 扫描进度 |
| `POST /api/dll/laser/on` `/off` | 开关激光 |
| `POST /api/dll/alignment/start` · `/api/dll/mpm/powers` | 对光 / 读功率 |
