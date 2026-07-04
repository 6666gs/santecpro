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

## 3. 三种用法

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

## 4. 结果保存

- 界面/`exporter.py` 导出兼容 Santec STS 软件的 CSV(14 行表头 + 数据)。
- 默认路径 `./scan_result_raw.csv`,可在界面修改。

## 5. 目录说明

```
remote-client/
├── run_ui.py               启动 PyQt5 界面(入口)
├── remote_sts_scan.py      命令行/SSH 扫描工具
├── config.py               默认配置(服务器地址等)
├── santecpro/
│   ├── remote.py           RemoteScanner(HTTP 客户端)
│   ├── ui_app.py / ui_controller.py  PyQt5 界面
│   ├── results.py          ScanResult / IL / 多量程合并(纯 numpy)
│   ├── reference.py        参考扫描 + IL 计算
│   ├── exporter.py         CSV 导出
│   ├── plotter.py          实时画图
│   ├── sweep_rules.py      扫描参数校验
│   ├── server_control.py   SSH 启动 Windows 服务
│   └── exceptions.py
├── tests/                  pytest
└── requirements.txt
```

## 6. 测试

```bash
pip install pytest
pytest
```
