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
python run_ui.py                  # 默认最大化
python run_ui.py --fullscreen     # 直接全屏
python run_ui.py --preview        # 不连接仪器，仅预览界面
```
启动后自动连接并检查激光状态；未开光时只开启一次，后台等待实际 LD_ON。就绪后填扫描参数并扫描。扫描结束或取消不关光；只有手动 Laser OFF 关光。地址修改后需重新连接。详见 [当前使用说明](../docs/USAGE_AND_VALIDATION.md)。

**B. Python API(脚本/集成)**
```python
from santecpro import RemoteScanner
sc = RemoteScanner("http://192.168.100.103:5000")
print(sc.check_instruments())
sc.prepare_laser(progress=print)  # 初始化一次，等待实际预热完成
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

**语法**(一行一条；注释放在独立一行，以 `#` 开头；下列行尾说明仅供阅读):
```text
job <名字>                          # 可选,命名输出文件夹
device "器件名字"                    # 可选,自动加入文件名
output "~/Measurements/santec"       # 可选,Mac 本地保存路径
wait 5s                             # 放在 scan 后面,保存后等待
set k=v ...                         # 可选默认:power range channels
scan <标签> <start> <stop> step=<v>{pm|nm} speed=<v> [power= range= channels= dir=]
```
- `start stop` 按蓝→红(低→高)写;`dir=forward`(默认)/ `reverse`(真实下扫)/ `both`(先正后反,展开成两段)。
- `step` 必带单位(`20pm` 或 `0.02nm`);`step`+`speed` 走 `sweep_rules` 校验。
- `<标签>` 单个词(可中文),用于文件名。

**示例**([jobs/example.scan](jobs/example.scan)):
```text
job example_device
set power=0 channels=1 range=1
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
- 未设置 `device` 时保留原文件名。输出:`scan_results/<job名>_<时间戳>/` 下每段一个 `NN_<标签>_<fwd|rev>_<raw|loss>.csv` + `manifest.json`(记录每段参数/方向/点数/成败/耗时)。

### 器件宽谱 + 精细扫描

直接修改 [jobs/device_two_pass.scan](jobs/device_two_pass.scan)：

```text
job two_pass
device "device_001"
output "~/Measurements/santec"
set power=0 range=1 channels=1
scan wide 1500 1630 step=1pm speed=20
wait 5s
scan fine 1545 1555 step=0.1pm speed=1
```

在 `remote-client` 目录、已安装客户端依赖的 Python 环境中运行：

```bash
python run_job.py jobs/device_two_pass.scan --dry-run
python run_job.py jobs/device_two_pass.scan --url http://WINDOWS_IP:5000
```

- `--dry-run` 只显示参数、文件名、等待时间和保存目录，不连接仪器。
- `output` 是 **Mac 本地目录**，支持 `~` 和带空格的引号路径；相对路径以 `.scan` 文件所在目录为基准。`--outdir` 优先覆盖它；两者都省略时用当前工作目录的 `scan_results`。
- 每次生成 `two_pass_<时间戳含微秒>/` 独立目录，不覆盖已有运行。示例文件名：`device_001_01_wide_1500-1630nm_1pm_20nms_fwd_raw.csv`、`device_001_02_fine_1545-1555nm_0.1pm_1nms_fwd_raw.csv`。`nms` 表示 nm/s，全部参数另存于 `manifest.json`。
- `wait 5s` 从前一段 CSV 和 manifest 写入完成后计时；不是从开始扫描计时。`dir=both` 后的等待发生在正反两次扫描都完成后；末尾的 wait 也会执行。默认扫描或保存失败就停止；显式 `--keep-going` 后可恢复的失败也会等待再继续。
- Ctrl+C 可中断等待、阻止下一段扫描；已经保存的文件保留。启动时检查并等待激光器就绪，扫描间隔与任务结束不关光。
- 默认保存 Raw。命令行任务与 GUI 内存会话独立，**不自动沿用 GUI reference**。需要 Loss 时，在脚本最前面额外加一段覆盖后续波长范围的线路 reference 扫描，再使用 `--reference-first --save loss`；reference 只存 Raw，程序暂停等你切换光路按 Enter，随后器件扫描内存保留 Raw/Loss，并导出 Loss。没有 reference 时不生成虚假的 Loss。

## 5. 结果保存

- 界面和批量脚本导出采用官方样本的 CSV 列名和 14 行元数据结构；尚未验证官方软件重新导入。
- 本次运行自行扫描设置 reference（只保存 Raw）；后续测量在内存同时保留 Raw/Loss，保存类型可选。
- Raw 包含波长、monitor 与各通道功率；Loss 为 reference − measurement（dB）。详见 [使用说明](../docs/USAGE_AND_VALIDATION.md#reference内存与-rawloss-导出)。
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

### 在界面中运行脚本

主界面顶部点击 **扫描脚本…**，可以直接编辑示例，或打开/另存 `.scan` 文件；连接仪器并等待激光就绪后点击 **运行脚本**。

- 每段扫描完成后，主图立即显示结果，加入扫描历史，并按脚本配置自动保存（不受主界面“自动保存”复选框影响）。参数栏同步显示正在执行的扫描参数。
- `wait 5s` 在保存完成后倒计时，期间可以查看 Raw/Loss、切换历史曲线；倒计时结束执行下一段。
- 点击 **暂停脚本** 可延长查看时间；若正在扫描，会先完成本段并保存。点击 **继续脚本** 立即跳过剩余查看等待，执行下一段。
- 在脚本窗口勾选 **每段结束后手动继续**，则每个中间结果都无限等待你点击继续，最后一段完成后直接结束。
- **停止脚本** 会停止后续步骤；正在扫描时同时请求取消本段。已保存文件和已有历史结果保留，激光保持开启。
- UI 脚本使用当前界面会话中实测的 Reference，导出类型在启动时读取主界面 Raw/Loss 选择，过程中保持固定；没有有效 reference 就没有 Loss。要测 reference，请先用主界面“扫描 Reference”，再运行器件脚本。
- 脚本运行时锁定仪器操作和手动扫描；默认任一扫描或保存失败就停止，不会悄悄继续下一段。

### GUI 历史缓存与平均时间

- 历史曲线保存在 Mac 内存，与导出的 CSV 独立。删除 CSV 不会同步删除历史；关闭程序后内存历史消失。
- GUI 超过 **20 条记录或 256 MiB 数组数据**时，自动释放最早已成功导出记录的 Raw/Loss。保留当前 Reference、最新结果、当前查看结果以及所有未保存/保存失败的记录；因此这是缓存目标，不是进程内存硬上限。未保存记录过多时请及时保存，运行日志会提示超额。
- `Reference` 菜单的“清理已保存历史”可立即释放旧数据；不删除磁盘文件。历史框悬停显示数组占用。被清理的记录不再出现在下拉框，原扫描编号及 Loss 的 Reference 编号保持不变。磁盘只保留你选择导出的 Raw 或 Loss，缓存清理后不能再从内存补导另一种。
- GUI 脚本只额外保留轻量执行摘要，已清理数组不会被脚本列表继续持有。命令行 `run_job` 的返回值仍保留各段记录，供 Python 调用者处理；上述自动清理策略仅用于 GUI。
- **脚本不需要 `averaging=`**，已从内置示例中移除。当前 NI USB-6210 / SPU 路径在 MPM 设置扫描采集后读取仪器实际平均时间，并用于 DAQ 和重采样；不是强行设定为 0.01 ms。旧脚本中的字段仍兼容解析，在此路径由仪器实际值覆盖。无 SPU 的旧路径仍保留原兼容行为。
- 更新 Windows 服务后，扫描响应和 Mac 导出 CSV 的平均时间元数据使用实际值；脚本 manifest 同样记录返回值。旧服务未返回实际值时，manifest 中未知值为 null。

导出的 Raw、Loss 和 Reference Raw 均在第 13 行记录本次扫描的 MPM Range 编号，例如 `Power meter range,,dBm,MPM range,3` 表示 Range 3。编号来自历史扫描结果，不随当前界面选项变化。原 dBm 量程字段仅在已有明确值时填写；Range 编号不当作 dBm。仍保留 14 行元数据及原数据列格式，列名中的 `R1` 仍表示导出曲线序号。此修正只需更新并重启 Mac 客户端；已在内存中的历史可重新导出，已有 CSV 不自动改写。

### 单波长对光监视

在“仪器 → 对光监视…”的小窗口中编辑激光波长（nm）和出射功率（dBm），点击“应用并开始监视”；运行期间可继续编辑并再次应用。窗口初始波长取扫描起点、初始功率取扫描功率，修改只在点击应用时发送。仪器会拒绝超出自身能力的参数。MPM 同步设置测量波长并启用单点 READ 自动量程，无需选扫描 Range；自动量程仍受模块物理测量范围限制。后续扫描会重新设置固定扫描 Range。

窗口以后台线程读数，关闭时等待正在执行的请求结束。打开期间主窗口不能启动扫描，避免同时改变仪器状态。停止和关闭均保持激光开启及最后应用的波长/功率，不重新开光或关光。必须同时更新 Windows 服务；旧服务无法确认自动量程和波长时会明确提示更新。

官方接口依据：[Python-IL-STS 的 set_read_range_mode](https://github.com/santec-corporation/Python-IL-STS/blob/main/src/santec/mpm_instrument_class.py#L404-L417)，使用 `Set_READ_Range_Mode(MPM.READ_Range_Mode.Auto)`。本项目以前在对光时误用了扫描用的 Manual 配置。

对光监视以 **100 ms（目标 10 次/秒）**为刷新周期；读取耗时计入周期，较慢时完成上一请求才发下一次，不并发堆积。状态栏显示实际完成读数的刷新率（包含网络及仪器耗时，并非保证仪器每次都生成独立新样本）。Windows 复用 MPM 连接，正常轮询不再每次 Connect/DisConnect；约 5–6 秒没有读数请求后自动释放连接，开始扫描/其他仪器操作前也先释放，发生读取错误则立即释放。停止/关闭窗口停止发读数请求，服务器短暂保留连接后释放，均不关光。

图窗上方的“X 轴缩放”是开关：启用后在曲线区域按住鼠标左键横向拖选波长范围，纵轴自动适配该范围内全部显示通道，可连续拖选进一步放大。“显示全部”恢复当前曲线的完整范围；切换历史、Raw/Loss 或 Reference 时自动恢复新曲线的完整视图。缩放只改变显示，不修改内存数据或 CSV。两个按钮不影响应用窗口的全屏状态。
