# remote-client — Santec 扫谱控制端

**部署在 Mac 或任意控制电脑上**,通过网络(HTTP)远程操控 [windows-server](../windows-server/) 执行扫描,并在本地画图、计算插入损耗(IL)、导出 CSV。**不接触仪器、DLL、GPIB。**

> 部署方式:把 **整个 `remote-client/` 文件夹** 拷到控制电脑即可。

---

## 1. 安装

```bash
cd remote-client
pip install -r requirements.txt
```

`requirements.txt` = `requests · numpy · matplotlib · PyQt5`(无需 pyvisa、无需 DLL)。

> **一步到位 + 自检(推荐)**:`python check_setup.py --install` 会先装依赖,再检查 Python/依赖,并 ping `SERVER_URL/api/status` 确认能连上 Windows 服务,打印 `✅ 就绪 / ❌ 缺什么`。测别的地址用 `--url http://IP:5000`。

## 2. 配置

改 [`config.py`](config.py) 或设环境变量(环境变量优先):

| 配置 | 默认 | config.py | 环境变量 |
|---|---|---|---|
| **服务器地址** | `http://192.168.100.103:5000` | `SERVER_URL` | `SANTEC_SERVER_URL` |
| TSL 地址(界面显示) | `GPIB3::1::INSTR` | `TSL_ADDRESS` | `SANTEC_TSL_ADDRESS` |
| MPM 地址(界面显示) | `GPIB0::16::INSTR` | `MPM_ADDRESS` | `SANTEC_MPM_ADDRESS` |
| SSH 用户 | `shareuser` | `SSH_USER` | `SANTEC_SSH_USER` |
| Windows 项目目录 | `E:\code_pro\windows_server` | `WINDOWS_DIR` | `SANTEC_WINDOWS_DIR` |
| Windows python.exe | `E:\code_pro\python312\python.exe` | `WINDOWS_PYTHON` | `SANTEC_WINDOWS_PYTHON` |

> **唯一必改项**:`SERVER_URL` 的 IP:端口 = Windows 电脑的实际 IP 和 `server.py` 端口。

## 3. 四种用法

**A. 图形界面(推荐)**
```bash
python run_ui.py
```
界面里确认服务器 URL → 填扫描参数 → 点“连接” → “扫描”。

**B. Python API(脚本/集成)**
```python
from santecpro import RemoteScanner
sc = RemoteScanner("http://192.168.100.103:5000")
print(sc.status())
result = sc.run_stsprocess_scan(start_wl=1550, stop_wl=1560, step=0.01, speed=20, power=0)
```

**C. 命令行 + SSH(无需服务常驻)**
```bash
python remote_sts_scan.py --start 1550 --stop 1560 --step-pm 10 --speed 20 --pull
```
经 SSH 登录 Windows 直接跑扫描脚本;`--pull` 用 SCP 把 CSV 拉回本地 `scan_results/`。
（SSH 免密可设 `export SANTEC_SSH_PASSWORD=...`,需系统装 `expect`。）

**D. 扫谱脚本(批量任务,语法见 §4)**
```bash
python run_job.py jobs/example.scan --dry-run   # 先看计划,不连硬件
python run_job.py jobs/example.scan             # 逐段自动扫并保存
```

## 4. 扫谱脚本(`.scan` 语法)

用一个文本脚本描述一次任务:多段扫描、不同范围、可双向(先蓝→红再红→蓝)。系统解析后逐段执行,每段存一个 CSV,并写 `manifest.json`。

**语法**(一行一条,`#` 为注释):
```text
job <名字>                          # 可选,命名输出文件夹
set k=v ...                         # 可选默认:power range channels averaging
scan <标签> <start> <stop> step=<v>{pm|nm} speed=<v> [power= range= channels= averaging= dir=]
```
- `start stop` 按蓝→红(低→高)写;`dir=forward`(默认)/ `reverse`(真实下扫)/ `both`(先正后反,展开成两段)。
- `step` 必带单位(`20pm` 或 `0.02nm`);`step`+`speed` 走 `sweep_rules` 校验。
- `<标签>` 单个词(可中文),用于文件名。

**示例**([jobs/example.scan](jobs/example.scan)):
```text
job example_device
set power=0 channels=1 range=1 averaging=0.01
scan broadband 1500 1600 step=20pm speed=50
scan resonance 1549 1551 step=1pm speed=10 dir=both
scan band_c    1530 1565 step=5pm speed=20 dir=reverse channels=1,2
```

**运行**:
```bash
python run_job.py my_job.scan --dry-run                          # 解析+校验+打印计划
python run_job.py my_job.scan --outdir ./scan_results --keep-going
```
- 遇错默认**停**;`--keep-going` 继续后续段。
- 输出:`scan_results/<job名>_<时间戳>/` 下每段一个 `NN_<标签>_<fwd|rev>.csv` + `manifest.json`(记录每段参数/方向/点数/成败/耗时)。

## 5. 结果保存

- 界面/`exporter.py` 导出兼容 Santec STS 软件的 CSV(14 行表头 + 数据)。
- 扫谱脚本每段输出 `wavelength_nm, chN_power_dbm..., monitor_dbm`。
- 默认目录:界面 `./scan_result_raw.csv`;脚本 `./scan_results/<job>_<时间戳>/`。

## 6. 目录说明

```
remote-client/
├── run_ui.py               启动 PyQt5 界面
├── run_job.py              扫谱脚本执行器(.scan)
├── remote_sts_scan.py      命令行/SSH 单次扫描
├── check_setup.py          环境自检
├── config.py               默认配置(服务器地址等)
├── jobs/example.scan       扫谱脚本示例
├── santecpro/
│   ├── remote.py           RemoteScanner(HTTP 客户端)
│   ├── jobscript.py        .scan 解析器(纯逻辑)
│   ├── job_runner.py       逐段执行 + 存 CSV/manifest
│   ├── ui_app.py / ui_controller.py  PyQt5 界面
│   ├── results.py          ScanResult / IL / 多量程合并
│   ├── reference.py · exporter.py · plotter.py
│   └── sweep_rules.py · server_control.py · exceptions.py
├── tests/                  pytest
└── requirements.txt
```

## 7. 测试

```bash
pip install pytest
pytest
```
