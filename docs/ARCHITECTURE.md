# santec 扫谱系统 — 架构与部署指南

本文档说明整个系统如何在 **两台电脑** 上分工、每一台需要放哪些文件、需要安装/配置什么，以及如何启动。

---

## 1. 为什么要两台电脑？

真正驱动仪器扫描的底层能力来自 Santec 官方的 **.NET DLL**（`STSProcess.dll` + `Santec.Instrument.dll`），这些 DLL **只能在 Windows 上通过 `pythonnet` 加载**。所以：

- **Windows 电脑**：物理连接仪器（GPIB），加载 DLL，真正执行扫描 —— 称为 **服务端**。
- **Mac / 任意电脑**：不接触仪器和 DLL，只通过 **网络（HTTP）** 远程下发扫描指令、拿回数据、画图存 CSV —— 称为 **控制端 / 客户端**。

一句话数据流：

```
控制端 UI/脚本 ──HTTP──▶ Windows 上的 Flask 服务 ──DLL──▶ GPIB ──▶ TSL 激光器 + MPM 功率计
                          （扫描结果按原路 JSON 返回，控制端画图 / 存 CSV）
```

---

## 2. 架构总览图

```
┌──────────────────────────────────────────┐          ┌───────────────────────────────────────────────┐
│  控制端  (Mac / 任意电脑)  “客户端”          │          │  Windows 电脑  “服务端”（唯一直连仪器的机器）       │
│                                            │          │                                                 │
│  根目录 santecpro/                          │          │  windows_server/                                │
│   ├ ui_app.py / ui_controller.py  PyQt5 界面│          │   ├ server.py          Flask，0.0.0.0:5000       │
│   ├ remote.py   RemoteScanner (HTTP 客户端) │   HTTP   │   ├ santec_dll_backend/  ◀ 真正的扫描逻辑          │
│   ├ sweep_rules.py  扫描参数校验             │ ───────▶ │   │    loader / instruments / scanner  (pythonnet)│
│   ├ reference.py    插入损耗(IL)计算         │  :5000   │   ├ stsprocess_api.py    HTTP 请求 ↔ DLL 适配层    │
│   ├ exporter.py / plotter.py  存 CSV / 画图  │          │   ├ santecpro/          核心库副本(deploy.sh 生成) │
│   └ server_control.py ──┐                   │          │   ├ vendor/santec_dll/  *.dll（需手动放入）        │
│  tools/remote_sts_scan.py│  SSH             │   SSH    │   └ scan_jobs/          服务端 CSV 输出目录        │
│                          └──────────────────│ ───────▶ │                                                 │
│                                            │          │   系统依赖: .NET Framework + NI-VISA 运行时 + GPIB 卡 │
└──────────────────────────────────────────┘          └────────────────────────┬────────────────────────┘
                                                                                │ GPIB
                                                                 ┌──────────────┴───────────────┐
                                                                 │ TSL-550 激光器   GPIB3::1::INSTR │
                                                                 │ MPM-210 功率计   GPIB0::16::INSTR │
                                                                 └──────────────────────────────┘
```

---

## 3. 职责划分速查表

| 组件 / 文件 | 放在哪台电脑 | 作用 |
|---|---|---|
| `windows_server/server.py` | **Windows** | Flask 服务，对外暴露 `/api/*` 接口 |
| `windows_server/santec_dll_backend/` | **Windows** | 通过 `pythonnet` 加载 DLL，执行 STSProcess 扫描（**核心**） |
| `windows_server/stsprocess_api.py` | **Windows** | 把 HTTP 请求参数转成 DLL 调用、把结果转成 JSON |
| `windows_server/vendor/santec_dll/*.dll` | **Windows** | Santec / NI / Keysight 专有二进制（**需手动放入**，未随仓库分发） |
| `windows_server/santecpro/` | **Windows** | 核心库副本（`deploy.sh` 从根目录生成，供 server 导入 SCPI 备用路径） |
| `windows_server/diagnose_*.py` | **Windows** | 调试脚本（可单机直接运行，不经 Flask） |
| 根目录 `santecpro/remote.py` (`RemoteScanner`) | **控制端** | HTTP 客户端，调用服务端 `/api/*` |
| 根目录 `santecpro/ui_app.py` + `ui_controller.py` | **控制端** | PyQt5 图形界面 |
| 根目录 `santecpro/sweep_rules.py` | **控制端** | 纯逻辑：下发前校验步长/速度组合 |
| 根目录 `santecpro/reference.py` | **控制端** | 纯逻辑：参考扫描 + IL 计算 |
| 根目录 `santecpro/exporter.py` / `plotter.py` | **控制端** | 存 CSV / 实时画图 |
| 根目录 `santecpro/server_control.py` | **控制端** | 通过 SSH 远程启动 Windows 上的 `server.py` |
| `tools/remote_sts_scan.py` | **控制端** | 命令行工具，SSH 远程跑扫描脚本 |
| 根目录 `santecpro/instruments/` + `scanner.py` | 两端都在，但**仅 Windows/Linux 有仪器时可用** | 直连 GPIB 的 SCPI 驱动（本地模式，见 §7） |

> **要点**：控制端真正“干活”的只有 `remote.py`（HTTP 客户端）+ UI + 几个纯计算模块。它**不需要仪器、不需要 DLL、不需要 GPIB**。

---

## 4. Windows 电脑（服务端）配置

### 4.1 需要拷贝的文件

把整个 **`windows_server/` 目录** 拷到 Windows 电脑即可（例如放到 `E:\code_pro\windows_server`，这是脚本里的默认路径）。它是自包含的：`server.py` 会优先导入自己目录下的 `windows_server/santecpro/` 副本，不依赖根目录的包或 `pip install santecpro`。

> `windows_server/santecpro/` 由根目录用 `python windows_server/deploy.sh` 生成。**改了根目录的核心库后要重新跑一次** deploy 再拷贝，否则两边会不一致。

### 4.2 需要安装的系统级依赖（这几项缺一不可）

| 依赖 | 用途 |
|---|---|
| **Windows 操作系统** | DLL 只能在 Windows 加载（`loader.py:21` 强制检查） |
| **.NET Framework**（4.5+） | `pythonnet` 靠它加载 `.dll` 程序集 |
| **NI-VISA 运行时** | GPIB 通信底层（或 Keysight IO） |
| **GPIB 硬件接口卡**（NI 等） | 物理连接 TSL / MPM |
| **Python 3.10+** | 运行服务（默认脚本路径 `E:\code_pro\python312\python.exe`） |

### 4.3 需要安装的 Python 包

```bash
cd windows_server
pip install -r requirements.txt
pip install pythonnet          # ⚠️ 关键，但当前 requirements.txt 漏了，必须手动装
```

`requirements.txt` 目前含 `flask / pyvisa / numpy / matplotlib / PyQt5 / requests`。其中：
- **必需**：`flask`、`numpy`、`pythonnet`（手动补）。
- **可选**：`pyvisa`（只有走 SCPI 备用路径时才需要；DLL 路径用不到）。
- **服务端用不到**：`matplotlib`、`PyQt5`（那是控制端画图/界面用的，装了也无妨）。

### 4.4 需要手动放入的 DLL

仓库出于版权原因**不分发** DLL。请从各厂商安装程序里取得下列文件，放进 `windows_server/vendor/santec_dll/`（详见 `windows_server/vendor/README.md`）：

```
vendor/santec_dll/
├── STSProcess.dll            (Santec IL-STS SDK)  ← 必需
├── Santec.Instrument.dll     (Santec 仪器 SDK)    ← 必需
├── NationalInstruments.*.dll (NI-VISA / DAQmx 运行时)
├── Ivi.Visa.dll / Keysight.Visa.dll
└── FTD2XX_NET.dll
```

`loader.py` 默认从 `windows_server/vendor/santec_dll/` 加载；缺文件会直接报 `FileNotFoundError`。

### 4.5 需要确认/配置的参数

| 配置项 | 默认值 | 在哪里改 |
|---|---|---|
| 监听地址 | `0.0.0.0`（所有网卡） | 启动参数 `--host` |
| 监听端口 | `5000` | 启动参数 `--port` |
| TSL 的 GPIB 地址 | `GPIB3::1::INSTR` | 启动参数 `--tsl` |
| MPM 的 GPIB 地址 | `GPIB0::16::INSTR` | 启动参数 `--mpm` |
| Windows 电脑的 IP | （由局域网决定，示例 `192.168.100.103`） | 需与控制端填的地址一致 |

> GPIB 地址要按你实际的仪器接线改（用 NI MAX 查看）。控制端每次请求也可以覆盖这些地址，但把服务端默认值设对最省心。

### 4.6 启动服务

```bash
cd E:\code_pro\windows_server
python server.py --host 0.0.0.0 --port 5000 --tsl GPIB3::1::INSTR --mpm GPIB0::16::INSTR
```

- 日志写到 `windows_server/server.log`。
- 服务端全局单例 + `RLock` 串行化仪器访问（同一时间只处理一个扫描）。
- 扫描是**阻塞式**：一个 `/api/scan/stsprocess` 请求会一直等到扫描完成再返回；控制端可另开 `GET /api/scan/state` 查询阶段（`idle → configured → stsprocess_running → completed/error`）。

### 4.7 关键 HTTP 接口

| 方法 & 路径 | 用途 |
|---|---|
| `GET  /api/status` | 健康检查 + 仪器连接状态 + IDN |
| `POST /api/scan/stsprocess` | **主扫描接口**（DLL 路径）。入参 `start_wl/stop_wl/step/speed/power/mpm_*`，返回波长、功率、各通道数据、CSV 路径 |
| `GET  /api/scan/state` | 查询扫描进度阶段 |
| `POST /api/dll/laser/on` `/off` | 开关激光 |
| `POST /api/dll/alignment/start` | 对光（实时读功率） |
| `POST /api/dll/mpm/powers` | 读 MPM 各通道当前功率 |
| `POST /api/tsl/command` / `/api/mpm/command` | 透传单条 SCPI 命令（调试用） |

---

## 5. 控制电脑（Mac / 客户端）配置

### 5.1 需要的文件

根目录的 `santecpro/` 包（正常 `pip install -e .` 或直接在仓库里跑）。控制端真正用到的是 `remote.py / ui_app.py / ui_controller.py / sweep_rules.py / reference.py / exporter.py / plotter.py / server_control.py`。

### 5.2 需要安装的 Python 包

```bash
pip install -r requirements.txt
pip install requests           # ⚠️ RemoteScanner 依赖它，但当前 requirements.txt 漏了
```

- **必需**：`requests`（HTTP 客户端，当前缺失需手动补）。
- **图形界面**：`PyQt5`、`numpy`、`matplotlib`。
- **不需要**：DLL、GPIB 卡、NI-VISA。（`pyvisa` 仅本地直连模式才需要；纯远程控制用不到。）

### 5.3 需要配置的参数

| 配置项 | 默认值 | 在哪里改 |
|---|---|---|
| 服务器地址（Windows 的 IP:端口） | `http://192.168.100.103:5000` | UI 里“服务器 URL”输入框（`ui_app.py:276`）；或调用 `RemoteScanner(server_url=...)` 时传入 |
| TSL / MPM 的 GPIB 地址 | `GPIB3::1::INSTR` / `GPIB0::16::INSTR` | UI 输入框，随请求下发给服务端 |
| 扫描参数（起止波长/步长/速度/功率/量程/通道） | 见 UI 默认 | UI 表单；步长速度组合受 `sweep_rules.py` 校验 |
| CSV 保存路径 | `./scan_result_raw.csv` | UI “保存路径” |

> 唯一必须对齐的关键项：**服务器 URL 里的 IP:端口** 要等于 Windows 电脑实际的 IP 和 `server.py` 的监听端口。

### 5.4 三种使用方式

**方式 A — 图形界面（推荐日常使用）**
```bash
python examples/scan_ui.py       # 启动 PyQt5 界面
```
在界面里填服务器 URL、扫描参数，点“扫描”。界面内部走 `RemoteScanner` → HTTP。

**方式 B — Python API（脚本 / 集成）**
```python
from santecpro import RemoteScanner
sc = RemoteScanner("http://192.168.100.103:5000")
print(sc.status())
result = sc.run_stsprocess_scan(start_wl=1550, stop_wl=1560, step=0.01, speed=20, power=0)
```

**方式 C — 命令行 + SSH（无需服务常驻）**
```bash
python tools/remote_sts_scan.py --start 1550 --stop 1560 --step-pm 10 --speed 20 --pull
```
它通过 SSH 登录 Windows，直接跑 `diagnose_stsprocess_scan.py`，`--pull` 会用 SCP 把 CSV 拉回本地 `scan_results/`。

### 5.5 结果保存位置

- **控制端**：UI/`exporter.py` 把数据存成兼容 Santec STS 软件的 CSV（14 行表头 + 数据）。
- **服务端**：若请求带 `csv_name`，DLL 路径会在 `windows_server/scan_jobs/` 也存一份。

### 5.6 SSH 相关配置（仅方式 C 和“远程启动服务”用到）

| 配置项 | 默认值 | 在哪里改 |
|---|---|---|
| SSH 用户名 | `shareuser` | `--user` / `server_control.py` 参数 |
| SSH 密码 | 读环境变量 `SANTEC_SSH_PASSWORD` | `export SANTEC_SSH_PASSWORD=...`（需装 `expect`） |
| Windows 上的项目目录 | `E:\code_pro\windows_server` | `--windows-dir` / 函数参数 |
| Windows 上的 python.exe | `E:\code_pro\python312\python.exe` | `--windows-python` / 函数参数 |

---

## 6. 两端必须一致的配置（对照）

| 配置 | Windows 端 | 控制端 | 必须一致？ |
|---|---|---|---|
| IP:端口 | `server.py --host/--port` + 本机 IP | UI 的“服务器 URL” | ✅ 必须一致 |
| TSL / MPM GPIB 地址 | `--tsl` / `--mpm` 默认值 | UI 输入 / 请求参数（可覆盖） | 建议一致 |
| DLL 目录 | `vendor/santec_dll/` 有真实 DLL | —（控制端无需） | 仅 Windows |
| SSH 路径/账号 | 真实存在的目录与账号 | `server_control.py` / CLI 常量 | ✅（用方式 C 时） |

---

## 7. 附：本地直连模式（可选，不经网络）

根目录的 `santecpro/scanner.py` + `instruments/` 是一套**纯 Python + PyVISA 的 SCPI 直连驱动**（项目最初的跨平台设计）。如果控制脚本就跑在**直接插着 GPIB 卡的 Windows/Linux** 上，可以不启服务、直接用 `Scanner` 类连仪器。

但注意：设计文档里已标注 MPM logging 的若干 SCPI 命令**尚未与官方手册核对**，这也是项目转向“Windows + DLL 服务”方案的原因。**生产扫描请以 DLL 路径（`/api/scan/stsprocess`）为准**，SCPI 直连仅作备用/调试。

在 Mac 上：`pyvisa` 找不到 GPIB 后端，本地模式不可用，**只能用远程模式**。

---

## 8. 端到端上手清单

**Windows（一次性）**
1. 拷入 `windows_server/`，放好 `vendor/santec_dll/*.dll`
2. 装 .NET Framework、NI-VISA、GPIB 驱动
3. `pip install -r requirements.txt && pip install pythonnet`
4. 接好 TSL / MPM，用 NI MAX 确认 GPIB 地址
5. `python server.py --host 0.0.0.0 --port 5000 --tsl GPIB3::1::INSTR --mpm GPIB0::16::INSTR`
6. 记下这台机器的局域网 IP

**控制端（Mac）**
1. `pip install -r requirements.txt && pip install requests`
2. `python examples/scan_ui.py`
3. 服务器 URL 填 `http://<Windows的IP>:5000`，先点状态/连接确认联通
4. 填扫描参数 → 扫描 → 存 CSV

---

## 9. 已发现的配置问题与建议

> 以下是本次梳理中发现、值得修复的点（不影响理解架构，但会影响“照着装就能跑”）：

1. **`windows_server/requirements.txt` 缺 `pythonnet`** —— DLL 路径的硬依赖，建议补上。
2. **根目录 `requirements.txt` 缺 `requests`** —— 控制端 `RemoteScanner` 的硬依赖，建议补上；同时 `pyvisa` 对纯远程的 Mac 客户端其实非必需，可考虑拆成 `requirements-client.txt` / `requirements-server.txt`。
3. **硬编码分散**：IP `192.168.100.103`、SSH 路径 `E:\code_pro\...`、GPIB 地址散落在 `ui_app.py` / `server_control.py` / `tools/remote_sts_scan.py`。建议集中到一个配置文件或环境变量，避免换环境时多处改。
4. **`windows_server/santecpro/` 是生成产物**：改根目录核心库后需重跑 `deploy.sh` 再部署，否则两边漂移。
