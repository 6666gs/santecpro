# 双文件夹重构 — 设计文档

**日期:** 2026-07-04
**状态:** 已确认
**目标:** 把项目重组为两个**自包含、可直接部署**的文件夹(Windows 服务端 / 遥控客户端),各带操作指南,让部署=拷贝一个文件夹。

## 背景

底层扫描依赖 Santec .NET DLL,只能在 Windows 上通过 `pythonnet` 加载。因此系统天然分为:
- **Windows 服务端**:直连仪器(GPIB)、加载 DLL、执行扫描,对外暴露 HTTP 接口。
- **遥控客户端**(Mac/任意电脑):通过 HTTP/SSH 远程下发指令、取数据、画图存 CSV。

当前仓库把两端代码混在根 `santecpro/` 包 + `windows_server/` + `examples/` + `tools/` 中,且 `windows_server/santecpro/` 是 `deploy.sh` 生成的副本。部署时需要理解这些关系,不够直观。

## 已确认的三项关键决策

1. **目录模型:两个自包含文件夹。** 各自携带全部所需代码(含少量共享小模块的副本)。
2. **迁移程度:彻底切换。** 代码整合进两个新文件夹,删除冗余的根 `santecpro/`、`examples/`、`tools/`、旧 `windows_server/`。
3. **客户端纯遥控。** 移除本地直连(pyvisa)模式;本地直连仅保留在 Windows 端作 SCPI 备用。

## 最终目录结构

```
santecpro/                      (仓库根)
├── windows-server/             ← 整包拷到 Windows 电脑
│   ├── server.py                   Flask 服务(读 config 默认值)
│   ├── santec_dll_backend/         loader / instruments / scanner —— pythonnet+DLL,核心扫描
│   ├── stsprocess_api.py           HTTP 请求 ↔ DLL 适配
│   ├── santecpro/                  SCPI 备用驱动子集:
│   │   ├── __init__.py             轻量(不在导入期拉 pyvisa/Qt)
│   │   ├── instruments/            base·tsl·mpm
│   │   ├── scanner.py              Scanner + ScanResult/ILMeasurement + merge/IL
│   │   ├── exceptions.py           (共享)
│   │   ├── sweep_rules.py          (共享)
│   │   └── exporter.py
│   ├── diagnostics/                diagnose_*.py(原散在根目录)
│   ├── vendor/santec_dll/          DLL(gitignore)+ README
│   ├── config.py                   HOST/PORT/TSL_ADDRESS/MPM_ADDRESS/DLL_DIR(env 可覆盖)
│   ├── requirements.txt            flask·pyvisa·numpy·pythonnet
│   ├── tests/                      DLL/SCPI 相关测试
│   ├── scan_jobs/                  服务端 CSV 输出(gitignore)
│   └── README.md               ← Windows 端操作指南
│
├── remote-client/              ← 整包拷到 Mac/控制电脑
│   ├── santecpro/
│   │   ├── __init__.py             导出 RemoteScanner / ScanResult / ILMeasurement
│   │   ├── remote.py               RemoteScanner(HTTP 客户端)
│   │   ├── ui_app.py               PyQt5 界面(移除本地模式分支,默认值读 config)
│   │   ├── ui_controller.py        仅远程路由
│   │   ├── results.py              ScanResult·ILMeasurement·merge_multi_range·calculate_il(纯 numpy)
│   │   ├── reference.py            IL 计算(从 results 导入)
│   │   ├── exporter.py             存 CSV(从 results 导入)
│   │   ├── plotter.py              实时画图
│   │   ├── sweep_rules.py          (共享)
│   │   ├── exceptions.py           (共享)
│   │   └── server_control.py       SSH 启动 Windows 服务(读 config)
│   ├── run_ui.py                   启动 UI(原 examples/scan_ui.py)
│   ├── remote_sts_scan.py          CLI/SSH 工具(原 tools/,读 config)
│   ├── config.py                   SERVER_URL/TSL_ADDRESS/MPM_ADDRESS/SSH_*(env 可覆盖)
│   ├── requirements.txt            requests·numpy·matplotlib·PyQt5
│   ├── tests/                      remote/reference/sweep_rules/ui/exporter/纯计算测试
│   └── README.md               ← 控制端操作指南
│
├── docs/
│   ├── ARCHITECTURE.md             总览(更新为新路径)
│   └── superpowers/specs/…         设计文档
├── sync_shared.py                  一键同步共享小模块(exceptions·sweep_rules)
├── README.md                       顶层:项目简介 + 指向两个文件夹指南
└── .gitignore
```

两个 `santecpro/` 包同名但内容不同,运行时各自从所在目录导入,互不干扰。

## 模块归属对照

| 原文件 | 去向 | 说明 |
|---|---|---|
| `windows_server/*`(server/backend/api/diagnose) | `windows-server/` | 直接迁移;diagnose_* 归入 `diagnostics/` |
| `santecpro/instruments/`、`scanner.py`(完整 Scanner) | `windows-server/santecpro/` | SCPI 备用路径 |
| `santecpro/remote.py`、`ui_app.py`、`ui_controller.py`、`plotter.py`、`reference.py`、`server_control.py` | `remote-client/santecpro/` | 客户端 |
| `santecpro/exporter.py` | **两端各一份** | 客户端存 CSV;Windows 端 SCPI 路径也用 |
| `santecpro/exceptions.py`、`sweep_rules.py` | **两端各一份(共享)** | 由 `sync_shared.py` 同步 |
| `scanner.py` 的纯计算部分 | `remote-client/santecpro/results.py` | 抽出 ScanResult/IL/merge,去硬件依赖 |
| `examples/scan_ui.py` | `remote-client/run_ui.py` | UI 入口 |
| `tools/remote_sts_scan.py` | `remote-client/remote_sts_scan.py` | CLI 工具 |
| 根 `santecpro/`、`examples/`、`tools/`、旧 `windows_server/`、根 `pyproject.toml`/`requirements.txt` | **删除** | 彻底切换 |
| `examples/debug_*.py`、`test_small.py`、根 CSV | 删除 | 一次性调试残留 |

## 配置抽取(解决硬编码分散)

**`windows-server/config.py`**(每项 `os.getenv` 覆盖):
- `HOST="0.0.0.0"`、`PORT=5000`、`TSL_ADDRESS="GPIB3::1::INSTR"`、`MPM_ADDRESS="GPIB0::16::INSTR"`、`DLL_DIR=vendor/santec_dll`
- `server.py` 的 argparse 默认值改为从 config 读取。

**`remote-client/config.py`**(每项 `os.getenv` 覆盖):
- `SERVER_URL="http://192.168.100.103:5000"`、`TSL_ADDRESS`、`MPM_ADDRESS`
- SSH:`SSH_USER="shareuser"`、`SSH_HOST`(从 SERVER_URL 推导或独立)、`WINDOWS_DIR=r"E:\code_pro\windows_server"`、`WINDOWS_PYTHON=r"E:\code_pro\python312\python.exe"`、`SSH_PASSWORD_ENV="SANTEC_SSH_PASSWORD"`
- `ui_app.py` 默认值、`server_control.py`、`remote_sts_scan.py` 全部改读 config。

结果:换环境时 IP/路径/GPIB 地址只在各自 `config.py`(或环境变量)一处改。

## 依赖修复

- `windows-server/requirements.txt`:`flask·pyvisa·numpy·pythonnet`(**补 pythonnet**)。
- `remote-client/requirements.txt`:`requests·numpy·matplotlib·PyQt5`(**补 requests、去 pyvisa**)。

## 共享代码防漂移

`exceptions.py`、`sweep_rules.py`(必要时 `exporter.py`)两端各存一份。`sync_shared.py` 以 `remote-client/` 版本为源(或独立 `shared/` 源)复制到两处;改动后跑一次校验一致。脚本同时提供 `--check` 模式,便于 CI/提交前核对。

## 测试策略

- 测试随代码走,两个文件夹各自 `tests/`,可独立 `pytest`。
- 调整 import 路径(去掉 `santecpro.` 顶层前缀或按新包结构)。
- DLL 相关测试在非 Windows 上继续自动 skip(现状如此)。
- 验收:两个文件夹分别 `pytest` 全绿(DLL 用例 skip 计入通过)。

## 部署流程(达成"简单快速")

**Windows 端**:拷 `windows-server/` → 放 `vendor/santec_dll/*.dll` → 装 .NET/NI-VISA/GPIB 驱动 → `pip install -r requirements.txt` → `python server.py`

**控制端**:拷 `remote-client/` → `pip install -r requirements.txt` → `python run_ui.py`(URL 指向 Windows 的 IP:5000)

## 不做(YAGNI)

- 不引入 monorepo 工具、命名空间包、workspace。
- 不做 PyPI 打包发布。
- 不保留根 `santecpro/`、`examples/`、`tools/` 作兼容层。

## 风险与缓解

- **大量文件移动 + import 重写**:分步提交,每步跑对应文件夹的 `pytest` 验证。
- **客户端删本地模式**:确认 UI/controller 无残留对 `Scanner`/`instruments` 的引用后再删依赖。
- **共享副本漂移**:靠 `sync_shared.py --check` 兜底。

## 收尾

1. 分步实现并逐步提交(每步验证)。
2. 更新 `docs/ARCHITECTURE.md` 为新路径与新部署命令。
3. 提交并推送到 GitHub(`origin/main`)。
