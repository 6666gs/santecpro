# 官方 SDK 配套依赖更新

这份更新保留 Mac 界面及 Windows Python 服务；不需要安装 LabVIEW。

## 使用步骤

1. 退出旧的 `server.py`。将压缩包解压到一个新目录，避免混入旧 DLL。
2. 在新 `windows-server` 目录运行 `python diagnostics\diagnose_daq.py`。
3. 成功标准：显示 `NationalInstruments.DAQmx, Version=17.6.45.181`，加载路径指向当前目录的 `vendor\santec_dll`，并在设备列表中出现 `Dev1`。
4. 成功后运行 `python server.py`，Mac 重新连接。
5. 先验证短范围 Reference（1545–1546 nm、1 pm、1 nm/s），与原官方软件对照后再执行宽谱扫描。

服务端默认 DAQ 名称为 Dev1。若以前设置过 SANTEC_DLL_DIR 或 SANTEC_NI_DAQMX_DLL 环境变量，确认它们没有指向旧目录。不要把单个 DLL 混入旧包后继续使用尚未退出的 Python 进程。

## 下载和核验内容

来源：Santec 官方 `LV_IL_Sample` 仓库固定提交 `1ed71d4173cfc9a7a99b909e4faca79cf41ca0a2`。

- 替换 NI-DAQmx：x64、17.6.45.181、PublicKeyToken=4febd62461bf11a4，与当前 InstrumentDLL 引用完全一致。
- 补充 NationalInstruments.Visa.dll 17.0.0.0。
- 保留已使用的 Santec.Instrument.dll、STSProcess.dll 和其他已有配套库；没有把上游较新的 InstrumentDLL 主库直接换入。
- 每个 DLL 的来源、SHA256、位数、程序集版本及引用记录在 `vendor\santec_dll\PROVENANCE.json`。
- 官方 x64 文件夹中的部分辅助组件版本并不统一，未盲目整目录覆盖。

加载器优先核对本地 NI DLL 的完整程序集标识，不再强制要求先在 GAC 中安装此程序集。某些纯托管 AnyCPU DLL 的 PE 标记为 0x14c 是正常的；NI-DAQmx 是混合程序集，必须为 0x8664。

## 验证边界

已经检查下载文件的 PE/CLR 元数据和直接关键依赖，并运行模拟测试。尚未在 Windows 实机加载这一组合或验证扫描。NI 原生驱动、其传递依赖与 Microsoft 运行库仍取决于 Windows 实际安装状态；本包不替代 NI 驱动安装程序，也不承诺仅复制 DLL 就能修复所有运行库问题。

若诊断仍失败，请提供完整输出。此时应按新的具体缺失依赖定位，不重复安装 LabVIEW 或更换 Python 位数。
