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

## 3. 放入 DLL(必需,仓库不分发)

从各厂商安装程序取得下列文件,放进 `vendor/santec_dll/`(详见 [vendor/README.md](vendor/README.md)):

```
vendor/santec_dll/
├── STSProcess.dll            ← 必需 (Santec IL-STS SDK)
├── Santec.Instrument.dll     ← 必需 (Santec 仪器 SDK)
├── NationalInstruments.*.dll (NI-VISA / DAQmx 运行时)
├── Ivi.Visa.dll / Keysight.Visa.dll
└── FTD2XX_NET.dll
```

缺文件启动时会报 `FileNotFoundError: Missing Santec DLLs`。

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
├── vendor/santec_dll/      DLL(需手动放入,已 gitignore)
├── tests/                  pytest(DLL 用例在非 Windows 上自动跳过)
└── requirements.txt
```

## 9. 测试

```bat
pip install pytest
pytest
```
