> 当前官方依赖更新请先阅读 [OFFICIAL_SDK_UPDATE.md](OFFICIAL_SDK_UPDATE.md)。已提供匹配的本地 x64 NI-DAQmx；下方关于缺少 GAC 的历史排查说明不代表仍须先补装 .NET 组件。

# windows-server — Santec 扫谱服务端

**部署在 Windows 电脑上**,直连 TSL-550 激光器和 MPM-210 功率计,加载 Santec DLL 执行扫描,对外提供 HTTP 接口。控制端(Mac/其他电脑)通过网络调用本服务。

> 部署方式:把 **整个 `windows-server/` 文件夹** 拷到 Windows 电脑即可。它是自包含的,不依赖仓库其它目录。

---

## 1. 系统前提(缺一不可)

| 依赖 | 用途 | 获取 |
|---|---|---|
| Windows 操作系统 | DLL 只能在 Windows 加载 | — |
| .NET Framework 4.5+ | `pythonnet` 加载 `.dll` 程序集 | Windows 自带 / 微软官网 |
| NI-VISA 运行时 | GPIB 通信 | NI 官网 |
| GPIB 接口卡(NI 等) | 物理连接仪器 | 硬件 |
| Python 3.10+ | 运行服务 | python.org |

## 2. 安装

```bat
cd windows-server
pip install -r requirements.txt
```

`requirements.txt` = `flask · pyvisa · numpy · pythonnet`。
（诊断脚本若要画图,可另装 `matplotlib`。）

> **一步到位 + 自检(推荐)**:`python check_setup.py --install` 会先装依赖,再逐项检查 Python 版本、依赖、DLL、pythonnet 加载、VISA/GPIB,并打印 `✅ 就绪 / ❌ 缺什么`。只想检查不安装就去掉 `--install`。

## 3. DLL(已随仓库提供,无需手动放入)

所需的 Santec/NI/Keysight DLL 已包含在 `vendor/santec_dll/`(即 `loader.py` 默认读取路径),**无需再手动获取**。详见 [vendor/README.md](vendor/README.md)。

> ⚠️ 这些是专有二进制,仅因本仓库为 **私有** 才随附;请勿将仓库改为公开或外传 DLL。

## 4. 配置

改 [`config.py`](config.py) 或设环境变量(环境变量优先),命令行参数再优先:

| 配置 | 默认 | config.py | 环境变量 | 命令行 |
|---|---|---|---|---|
| 监听地址 | `0.0.0.0` | `HOST` | `SANTEC_HOST` | `--host` |
| 监听端口 | `5000` | `PORT` | `SANTEC_PORT` | `--port` |
| TSL 地址 | `GPIB3::1::INSTR` | `TSL_ADDRESS` | `SANTEC_TSL_ADDRESS` | `--tsl` |
| MPM 地址 | `GPIB0::16::INSTR` | `MPM_ADDRESS` | `SANTEC_MPM_ADDRESS` | `--mpm` |
| DLL 目录 | `vendor/santec_dll` | `DLL_DIR` | `SANTEC_DLL_DIR` | — |

> GPIB 地址用 NI MAX 查看后填对即可。

## 5. 启动

启动前建议先跑 `python check_setup.py` 确认环境就绪(见 §2)。

```bat
python server.py
:: 或显式指定
python server.py --host 0.0.0.0 --port 5000 --tsl GPIB3::1::INSTR --mpm GPIB0::16::INSTR
```

- 日志写到 `server.log`。
- 记下这台电脑的局域网 IP,控制端要连 `http://<该IP>:5000`。
- 扫描 CSV(若请求带 `csv_name`)输出到 `scan_jobs/`。

## 6. 验证联通

浏览器或控制端访问 `http://<IP>:5000/api/status` 应返回 JSON(含 `tsl_idn` / `mpm_idn`)。

详见 [当前使用说明与硬件验收](../docs/USAGE_AND_VALIDATION.md)。`POST /api/dll/check` 检查真实仪器，`POST /api/dll/laser/prepare` 初始化激光并报告预热状态，`POST /api/scan/cancel` 请求取消扫描而不关光。

## 7. 主要 HTTP 接口

| 方法 & 路径 | 用途 |
|---|---|
| `GET  /api/status` | 健康检查 + 仪器状态 |
| `POST /api/scan/stsprocess` | **主扫描接口**(DLL 路径) |
| `GET  /api/scan/state` | 查询扫描进度 |
| `POST /api/dll/laser/on` `/off` | 开关激光 |
| `POST /api/dll/alignment/start` | 对光(实时读功率) |
| `POST /api/dll/mpm/powers` | 读各通道功率 |

## 8. 目录说明

```
windows-server/
├── server.py               Flask 服务(入口)
├── config.py               默认配置
├── stsprocess_api.py       HTTP 请求 ↔ DLL 适配
├── santec_dll_backend/     pythonnet 加载 DLL、执行扫描(核心)
├── santecpro/              SCPI 备用驱动子集(instruments/·scanner 等)
├── diagnostics/            诊断脚本(可单独运行,不经 Flask)
├── vendor/santec_dll/      DLL(已随仓库提供)
├── tests/                  pytest(仪器使用模拟对象)
└── requirements.txt
```

## 9. 测试

```bat
pip install pytest
pytest
```

### NI USB-6210 / Dev1 采集修复

当前实验系统使用 TSL-550 + MPM-210 + NI USB-6210（NI MAX 名称 `Dev1`）。服务端默认 `DAQ_DEVICE="Dev1"`，通过官方 `Santec.SPU` 获取实际触发/Monitor 数据；Mac 无需增加 DAQ 配置。Windows 需安装 NI-DAQmx（含 .NET Framework 支持），并保留官方软件正常扫描时的接线。

旧版本错误 `Get_216_Triggerdata ... -20` 来自 DLL 对模块固件的限制；重试同类接口不能代替 DAQ。新路径：连接 SPU → MPM 自由采集配置（triggerstep=0）→ 读取实际平均时间 → 启动 DAQ → TSL soft trigger → 等待采集 → 读取 DAQ → `Freerun_SPU` 重采样。禁止用合成触发或 Monitor 数据替代失败采集。

更新整个 Windows 服务端目录后，退出旧 `server.py`，在新目录启动：

```powershell
$env:SANTEC_DAQ_DEVICE = "Dev1"
python diagnostics/diagnose_daq.py
python server.py
```

诊断只枚举 DAQ 和 DLL 方法，不开光、不扫描。先用 1545–1546 nm、1 pm、1 nm/s 扫描 Reference 验收，再进行宽谱扫描。DAQ 采集失败时不导出结果；取消、异常及正常结束均释放采集任务，不关闭激光。若其他硬件确实支持 MPM 内置触发读取，可在 `config.py` 将 `DAQ_DEVICE` 改为空字符串来禁用 SPU 路径，不应对本套 Dev1 系统这样设置。

依据：[Santec 官方 DAQ 接口示例](https://github.com/santec-corporation/Python-IL-STS/blob/main/src/santec/daq_device_class.py)、[官方 STS 顺序与 Freerun_SPU](https://github.com/santec-corporation/Python-IL-STS/blob/main/src/santec/sts_process.py)。同时核对了项目内 DLL：`Set_Sampling_Parameter` 返回 void；`Sampling_Start(True)` 启动异步采集，支持轮询 `IsSampling` 与 `Logging_Errorcode`。本地模拟测试不代替 Dev1 实机验收。

### DAQmx `BadImageFormatException`（DLL 位数冲突）

项目原有 `vendor/santec_dll/NationalInstruments.DAQmx.dll` 是 x86 混合程序集，而 `Santec.Instrument.dll` 和 `STSProcess.dll` 是 x64，不能一起加载。**保留 64 位 Python**。新加载器不再按路径强制加载这份 NI DLL，而是按 Santec SDK 引用的完整程序集标识交给 Windows .NET Framework 及 NI 安装程序注册的 publisher policy 解析，再验证实际加载的是 x64。

`python diagnostics/diagnose_daq.py` 会先打印 Python 位数、项目 DLL 架构、系统 GAC 中 NI DAQmx 的路径与版本，再尝试枚举 Dev1。如果找不到兼容程序集，需安装/修复 NI-DAQmx 的 **.NET Framework 支持**及版本策略；能在 NI MAX 看见 Dev1，并不证明 .NET 支持已安装。不要从任意目录复制一个同名 DLL，也不要盲目启用程序集绑定日志注册表项。请保留诊断的完整输出，用于核对具体版本。

高级覆盖 `SANTEC_NI_DAQMX_DLL` 仅接受 x64、且完整程序集标识与 SDK 引用一致的 DLL；不同版本需要 NI 安装程序的兼容策略，不自动强制改绑。依据：[NI .NET 支持说明](https://knowledge.ni.com/KnowledgeArticleDetails?id=kA00Z0000019MOCSA2)。

若输出中的 `Installed NI .NET assemblies` 为空，且随后 pythonnet 又从 vendor 加载 x86 DLL，说明旧加载器仍允许自动回退。新版在缺少已注册 x64 程序集时提前停止；加载 Santec SDK 前会将 vendor 内已知的 x86 DAQmx DLL 重命名为 `.x86-disabled`（保留原文件，不覆盖已有备份），阻止 resolver 回退。

先运行 `python diagnostics/diagnose_ni_install.py`：这是标准库独立脚本，不加载 clr 或任何 DLL、不操作设备、不修改文件。它检查 GAC、National Instruments 安装目录和 IVI 目录；GAC 为空不等于整台电脑没有 .NET 程序集。根据输出再选择安装 NI-DAQmx 的 .NET Framework 支持，或核对已有 x64 程序集的完整版本标识。看到 NI MAX 的 Dev1 仅说明设备驱动一侧可用。

### 对光监视：波长、功率与自动量程

`POST /api/dll/alignment/start` 接受 `wavelength`（nm，省略为1550）、`power`（dBm）、`mpm_module` 和 `mpm_channels`。设置 TSL 波长/功率及 MPM 测量波长，调用官方 `Set_READ_Range_Mode(Auto)`，然后返回单点功率；响应含 `range_mode: auto` 和已提交的 `wavelength`、`power`。这些是成功提交的设置值，不是独立光功率实测值。旧 `mpm_range` 参数在此接口忽略，扫描路径仍显式设置 Manual 及固定 Range。接口不执行 LD/快门切换。

对光刷新优化：`alignment_cache.py` 在仪器锁保护下复用 MPM 连接，读数失败、地址改变或进入其他仪器操作时释放。后台每秒检查一次，闲置达到 5 秒后释放通信连接（不更改 LD/快门）。每次 `/api/dll/mpm/powers` 仍读取真实仪器，不返回缓存功率值。需随 `server.py` 一起部署该文件。
