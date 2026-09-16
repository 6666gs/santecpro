# 当前版本部署与仪器验收

## 激光生命周期

打开 `run_ui.py` 后，界面自动用当前 URL/GPIB 配置连接 Windows，读取实际仪器身份。

- 已经 `LD_ON`：直接复用，不重复发送开光指令。
- 未开启：发送一次开光指令，每 2 秒检查实际 LD 状态，显示“预热中”。
- 只有读回 `LD_ON` 才打开快门并允许扫描；不是发送开光指令成功就认为预热完成。
- 默认等待上限 900 秒。超时不关光，可再次连接继续检查；Python API 可传 `prepare_laser(timeout=...)`。
- 扫描开始、完成、失败、取消、界面断开和关闭，都不自动开关激光或快门。
- 只有手动 `Laser OFF` 会关闭快门和激光。手动 `Laser ON` 同样等待预热。
- 批量 CLI 在任务开始前初始化一次，之后各段扫描不切换激光状态。

启动界面会尝试初始化真实仪器。只想检查环境且不改变激光状态时，运行 `check_setup.py`，或调用 `RemoteScanner.check_instruments()`。

## 部署

Windows：完整更新 `windows-server/`（包括 `santec_dll_backend/`、`santecpro/` 和 vendor DLL）。使用 Python 3.10+、匹配位数的仪器驱动和运行环境。先确认 GPIB 与触发连线。

```bat
cd windows-server
python check_setup.py --install
python server.py --tsl GPIB3::1::INSTR --mpm GPIB0::16::INSTR
```

服务启动参数和环境变量现在作为 DLL 默认地址。客户端明确传入的地址优先。
`SANTEC_DLL_DIR` 可指定 DLL 目录。Mac 与 Windows 需要网络互通，Windows 防火墙允许局域网访问服务端口。

Mac：完整更新 `remote-client/`，使用 Python 3.10+ 的虚拟环境：

```bash
cd remote-client
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export SANTEC_SERVER_URL="http://你的Windows_IP:5000"
export SANTEC_TSL_ADDRESS="GPIB3::1::INSTR"
export SANTEC_MPM_ADDRESS="GPIB0::16::INSTR"
python check_setup.py
python run_ui.py
```

启动时地址不正确会报告连接失败；在界面修改后点“连接”重试。`/api/status` 是服务状态，不代表仪器此刻已就绪；界面的连接初始化使用 `/api/dll/check` 与 `/api/dll/laser/prepare`。

## 批量与 Python 调用

```bash
python run_job.py jobs/example.scan --dry-run
python run_job.py jobs/example.scan --tsl GPIB3::1::INSTR --mpm GPIB0::16::INSTR
```

`--dry-run` 不连接仪器。执行任务前会检查硬件并等待预热。Ctrl+C 在扫描执行期间请求取消；已完成段的 manifest 会保留。`--keep-going` 不会越过明确的取消、连接中断或请求超时继续扫描。

```python
from santecpro import RemoteScanner

scanner = RemoteScanner("http://你的Windows_IP:5000")
scanner.set_addresses("GPIB3::1::INSTR", "GPIB0::16::INSTR")
print(scanner.check_instruments())  # 仅查询，不开光
scanner.prepare_laser(timeout=900, progress=print)  # 一次初始化
result = scanner.run_stsprocess_scan(
    start_wl=1550, stop_wl=1550.1, step=0.01, speed=1,
    power=0, plot=False, save_csv="scan.csv",
)
# 后续扫描直接复用已开启的激光，不必重复初始化。
```

## 取消与测量错误

界面“取消扫描（保持激光开启）”调用 `POST /api/scan/cancel`。
返回 202 只表示请求已接受，最终结果以扫描请求和 `GET /api/scan/state` 为准。
服务端在扫描状态轮询和处理阶段检查取消，停止扫波和功率计 logging，并保持激光状态。
单次 DLL/GPIB 调用仍可能阻塞，因此这是协作式取消，不是硬件急停。
并发仪器请求返回 HTTP 409，不会排队等上一次扫描结束后意外执行。

无法读取真实 trigger/monitor 时扫描报错，不再合成数据。程序也会检查采集点数、有限数值、重采样长度、波长方向和范围；异常不导出为成功结果。
`csv_name` 仅接受文件名，Windows 端输出固定在 `scan_jobs/`。
HTTP 超时不等于仪器已经停止；发生通信中断后先检查服务端扫描状态，不要直接重试。

## 必须在仪器上完成的验收

本地自动测试使用模拟仪器，不证明真实 DLL/驱动兼容、物理下扫或计量精度。

1. 激光已开启时启动界面：确认不重启 LD。
2. 激光关闭时启动界面：确认只发一次开光，等待真实 LD_ON，再允许扫描。
3. 用仪器支持的小波段、单通道正扫：与官方软件对照波长、峰位、功率和点数。
4. 改非默认 GPIB 地址，确认检查、扫描和手动激光控制使用同一设备。
5. 扫描中取消：确认扫波/logging 停止，LD 保持开启；再次扫描无需预热。
6. 验证多通道与反扫；反扫必须实际产生降序波长数据，不能仅靠交换请求参数判定。
7. 模拟 trigger/monitor 读取故障：应报错，不产生假成功谱线。

服务只应部署在受控实验室网络；当前 HTTP API 没有身份认证。尚未实现断线续传或任务恢复。

## Reference、内存与 Raw/Loss 导出

Reference 必须在本次运行中自行扫描设置，没有官方预设 reference，也不从磁盘加载旧 reference。

1. 接好用于扣除线路响应的参考光路，点击“扫描并设置 Reference”；也可先扫描，再点“将所选扫描设为 Reference”。Reference 只支持 Raw 导出。
2. 切换到待测器件光路，再执行普通扫描。只要 reference 的模块、通道和波长范围匹配，每次扫描完成就同时在内存中保留 Raw 和 Loss。
3. “显示 Raw / 显示 Loss”只决定图上显示哪份数据；保存类型单独选择 Raw 或 Loss。先保存一种后，可切换并保存另一种，无需重扫。
4. 扫描历史保留本次运行的所有扫描，可选择之前的扫描查看、导出。更换或清除 reference 不会重算或删除之前测量已缓存的 loss；新 reference 只影响之后的扫描。
5. 尚未设置 reference，或其通道、模块、波长覆盖不匹配时，保留 Raw，明确显示 Loss 不可用，不生成假 loss。关闭软件会释放内存历史，所需结果应先保存。

Loss 当前采用**正值插入损耗**：`reference_dBm - measurement_dBm`；reference 插值到测量波长点。不自动使用 monitor 做漂移归一化，不声称等同官方软件的归一化算法。Monitor 始终保留在 Raw 中。

导出使用样本中的 14 行元数据结构，第 15 行为列名：

- Raw：`Wavelength(nm),Monitor-R1(dBm),Raw_M1-Ch1-R1(dBm),,`，数据 5 位小数；多通道增加相应列。
- Loss：`Wavelength(nm),IL_M1_CH1,,,`，数据 8 位小数；多通道增加相应列。
- 软件字段如实标为 `santecpro`，无法获取的设备细节留空，不复制历史样本的序列号或 USB-6210 信息。
- 界面文件名使用 `_raw.csv` / `_loss.csv`；重名时增加序号，避免覆盖已保存的扫描。

批量脚本可将**展开后的第一段扫描**作为 reference（应将完整参考波段写为第一段，使用 `dir=forward`）：

```bash
python run_job.py my_job.scan --reference-first --save raw
python run_job.py my_job.scan --reference-first --save loss
```

Reference 段始终保存 Raw；完成后 CLI 等待你切换到器件光路并按 Enter，才开始后续段。Reference 失败时任务停止，即使指定 `--keep-going`。后续每段内存记录都保留 Raw 和可用的 Loss，`--save` 只决定写出哪一种。CLI 退出时内存释放；Python 调用者可通过返回结果的 `.record` 或传入 `ScanSession` 保留两份数据继续导出。

## Mac 界面与全屏

界面默认最大化，保留系统菜单栏；点击右上角“进入全屏”或按 **Control–Command–F** 进入 macOS 全屏，**Esc** 退出。也可以使用 Mac 窗口的绿色全屏按钮。

主界面没有滚动区域：顶部是波长、步长、速度、功率和通道；中央为扫描历史、Raw/Loss 显示选择和谱图；底部为 reference、器件扫描、取消与保存。

- **设置 → 连接**：服务器地址、GPIB 地址与服务启动。
- **设置 → 采集**：MPM 量程、模块和扫描模式。
- **设置 → 保存**：CSV 保存路径。
- **仪器**菜单：手动开关激光、对光监视。
- **Reference**菜单：设置、查看、保存 raw、清除 reference。
- 完整运行日志在独立窗口查看，不占用主界面高度。

支持的最小窗口为 900×560（Qt 逻辑像素）。自动布局检查覆盖 900×560、1024×640、1280×800、1440×900、1728×1117；真实 Mac 窗口已检查全屏按钮、全屏快捷键和 Esc 返回。

```bash
python run_ui.py                 # 默认最大化，正常连接并初始化仪器
python run_ui.py --fullscreen    # 直接进入全屏
python run_ui.py --windowed      # 普通可调整窗口
python run_ui.py --preview       # 示例谱图，仅预览布局，不连接或操作仪器
```

## 重复扫描脚本与延时

新增可直接修改的 `remote-client/jobs/device_two_pass.scan`：1500–1630 nm、1 pm、20 nm/s 扫描并保存，等待 5 s，再进行 1545–1555 nm、0.1 pm、1 nm/s 扫描并保存。`device` 设置器件名，`output` 设置 Mac 本地目录，`wait` 设置保存后的等待秒数。每次运行创建独立目录，文件名包含器件名、序号、标签、范围、步长、速度、方向和 Raw/Loss 类型。完整语法和运行命令见 [客户端说明](../remote-client/README.md#器件宽谱--精细扫描)。

已用模拟扫描器验证保存→等待→下一段顺序、等待中断、保存失败停止和同名运行目录保护；CLI dry-run 验证不连接硬件。两组参数尚需实际仪器运行验收。
