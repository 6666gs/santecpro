# 扫谱脚本(Scan Job DSL)— 设计文档

**日期:** 2026-07-04
**状态:** 已确认
**目标:** 让用户用一个行式脚本(`.scan`)描述一次扫谱任务(多段、不同范围、可双向),系统解析后逐段自动执行并保存数据。全部在 `remote-client`,不改服务端。

## 背景

用户经常测器件透射谱:既要宽谱、也要固定小范围,某些范围还要先蓝→红扫一次再红→蓝扫一次(捕捉方向相关效应)。目前只能一段段手动在界面里跑。需要一个可编码、可批处理的"扫谱脚本"。

## 已确认决策

1. **形式**:行式自定义 DSL(非 YAML、非 Python)。
2. **reverse 语义**:真实下扫 —— reverse 段把 `start/stop` 对调后下发,激光从高波长物理扫到低波长。
3. **运行**:先做 CLI(`run_job.py`),UI 集成以后再说。
4. 文件后缀 `.scan`;遇错默认**停**(`--keep-going` 可继续);`set` 做全局默认。

## DSL 语法

```text
# 整行注释;空行忽略
job <名字>                       # 可选,命名输出文件夹
set k=v [k=v ...]               # 可选,设默认值,作用于其后的 scan(可多次)
scan <标签> <start> <stop> step=<v>{pm|nm} speed=<v> [power= range= channels= averaging= dir=]
```

- `start stop`:按蓝→红(低→高)写。`dir` 决定物理方向:
  - `forward`(默认)= start→stop
  - `reverse` = stop→start(下发时对调,真实下扫)
  - `both` = 先 forward 再 reverse(展开成两段)
- `step`:必填,带单位 `pm` 或 `nm`(如 `20pm`、`0.02nm`);缺单位报错。
- `speed`:必填(nm/s)。`step`+`speed` 走现有 `sweep_rules.validate_sts_sweep_params` 校验。
- `power`(dBm)、`range`(1-5)、`channels`(如 `1,2`)、`averaging`(ms):可选,缺省取 `set` 值,再缺取内置默认。
- `<标签>`:单个词(可中文、无空格),用于文件名。

**内置默认:** `power=0.0 range=1 channels=1 averaging=0.01`。

### 示例

```text
# 器件 A 透射谱任务
job deviceA_transmission
set power=0 channels=1 range=1 averaging=0.01

scan broadband 1500 1600 step=20pm speed=50
scan resonance 1549 1551 step=1pm speed=10 dir=both
scan band_c    1530 1565 step=5pm speed=20 dir=reverse channels=1,2
```

## 运行方式

```bash
python run_job.py my_job.scan                     # 执行
python run_job.py my_job.scan --dry-run           # 只解析+校验+打印计划,不连硬件
python run_job.py my_job.scan --url http://IP:5000 --outdir ./scan_results --keep-going
```

`--url` 缺省取 `config.SERVER_URL`;`--outdir` 缺省 `./scan_results`。

## 输出组织

```
<outdir>/<job名>_<YYYYMMDD_HHMMSS>/
├── 01_broadband_fwd.csv
├── 02_resonance_fwd.csv
├── 03_resonance_rev.csv
├── 04_band_c_rev.csv
└── manifest.json
```

- 每段 CSV:`wavelength_nm, ch1_power_dbm[, ch2...], monitor_dbm`(与后端 `_write_csv` 一致)。
- `manifest.json`:任务名、时间戳、每段(标签/方向/start_wl/stop_wl/step/speed/power/range/channels/averaging/csv 文件名/点数/ok/error/耗时)。

## 代码结构(全在 remote-client)

| 文件 | 职责 |
|---|---|
| `santecpro/jobscript.py` | 纯解析器:`parse_job(text) -> JobSpec`;`Segment`/`JobSpec`(frozen dataclass);展开 `dir=both`;`sweep_rules` 校验;错误带行号 |
| `santecpro/job_runner.py` | `run_job(job, scanner, outdir, timestamp, keep_going, log) -> list[SegmentResult]`:逐段调用 `RemoteScanner.run_stsprocess_scan`,写 CSV + manifest |
| `run_job.py` | CLI 入口(解析 argv、连接、调用 runner) |
| `tests/test_jobscript.py` | 解析/校验/方向展开/默认值/注释 单测(纯,无硬件) |
| `tests/test_job_runner.py` | mock scanner 的 runner 单测(校验每段调用参数、reverse 对调、CSV/manifest 写出) |
| `jobs/example.scan` | 模板 |

### 数据类型

```python
@dataclass(frozen=True)
class Segment:
    label: str
    start_wl: float          # 已按方向解析(reverse 已对调)
    stop_wl: float
    step: float              # nm
    speed: float             # nm/s
    power: float
    mpm_range: int
    mpm_channels: tuple[int, ...]
    mpm_averaging_time_ms: float
    direction: str           # "fwd" | "rev"

@dataclass(frozen=True)
class JobSpec:
    name: str
    segments: tuple[Segment, ...]
```

- 复用 `RemoteScanner.run_stsprocess_scan(start_wl, stop_wl, step, speed, power, mpm_range, mpm_channel, mpm_channels, mpm_averaging_time_ms, plot=False, save_csv=None)`,返回 `ScanResult`;runner 从其 `wavelengths/channel_powers/monitor_powers` 写 CSV。

## 错误处理

- **解析错误**:`第 N 行: <原因>`,扫描前退出(不连硬件)。
- **运行前统一校验**所有段(step/speed/span via sweep_rules)→ 有错先退。
- **某段扫描异常**:记入 manifest;默认遇错即停,`--keep-going` 继续后续段。
- `--dry-run`:解析+校验+打印计划,绝不连硬件/扫描。
- reverse 是真实下扫;若某台 TSL/DLL 不支持 start>stop,会在该段抛错并记入 manifest(需硬件验证)。

## 测试策略

- 解析器:合法脚本→正确 `JobSpec`;非法 step/speed/键/缺单位→带行号报错;`dir=both` 展开为 fwd+rev 且 rev 已对调;`set` 默认应用与覆盖;注释/空行。
- runner:mock `RemoteScanner`,断言每段 `run_stsprocess_scan` 入参正确(尤其 reverse 的 start/stop 对调)、CSV 与 manifest 写出、遇错即停 vs `--keep-going`。
- 目标:`remote-client` 全套 `pytest` 全绿。

## 不做(YAGNI)

循环/变量/条件、`repeat=N`、UI 集成、仪器波长上下限硬校验、断点续跑。
