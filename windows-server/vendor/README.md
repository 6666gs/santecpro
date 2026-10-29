# Vendor DLLs(需自行获取)

Windows 服务端通过 `pythonnet` 加载一组 Santec / NI / Keysight 的 .NET DLL。
这些是各厂商的专有二进制,**不包含在本仓库中**(已被 `.gitignore` 忽略,也已从 git 历史中清除)。
使用前请自行获取,并放入本目录下的 `santec_dll/`:

```
windows-server/vendor/santec_dll/
├── STSProcess.dll                          Santec 扫描核心
├── Santec.Instrument.dll                   Santec 仪器库(上游文件名为 InstrumentDLL.dll)
├── FTD2XX_NET.dll                          FTDI D2XX 托管封装
├── Ivi.Visa.dll
├── Keysight.Visa.dll
├── NationalInstruments.Common.dll
├── NationalInstruments.DAQmx.dll           必须是 x64(PE machine 0x8664)
├── NationalInstruments.NI4882.dll
├── NationalInstruments.NiLmClientDLL.dll
├── NationalInstruments.Visa.dll
├── NationalInstruments.VisaNS.dll
└── PROVENANCE.json                         (已在仓库中)来源、版本、SHA256 清单
```

`loader.py` 默认读取该目录;也可用环境变量 `SANTEC_DLL_DIR` 指向其他目录。

## 获取方式

### 方式 A:从 Santec 官方示例仓库获取(最省事)

Santec 官方在 GitHub 上公开了 LabVIEW 示例工程,其中带有上述全部 DLL:
<https://github.com/santec-corporation/LV_IL_Sample>(目录 `LV_IL_Sample/DLL/x64/`)。

本项目验证过的是固定提交 `1ed71d4173cfc9a7a99b909e4faca79cf41ca0a2`,单个文件的下载地址形如:

```
https://raw.githubusercontent.com/santec-corporation/LV_IL_Sample/1ed71d4173cfc9a7a99b909e4faca79cf41ca0a2/LV_IL_Sample/DLL/x64/<文件名>
```

注意:

- 上游把 `Santec.Instrument.dll` 叫作 `InstrumentDLL.dll`;本项目使用的是 **2.9.1.0** 版本,放入时需**重命名为 `Santec.Instrument.dll`**。上游较新的版本未经本项目验证,不要直接替换。
- `NationalInstruments.Visa.dll` 在上游位于 `DLL/` 根目录,不在 `x64/` 下。
- 上游 `x64/` 目录里并非每个文件都是 64 位,各文件的版本和位数不统一,见下表。**只有 `STSProcess.dll`、`Santec.Instrument.dll` 和 `NationalInstruments.DAQmx.dll` 必须是 x64**,其余纯托管 DLL 的 PE 标记为 `0x14c` 是正常的。
- 上游仓库没有声明许可证,使用前请自行确认你的使用方式符合 Santec 的条款。

### 方式 B:从厂商安装包获取

| DLL | 来源 |
|---|---|
| `STSProcess.dll`、`Santec.Instrument.dll` | 随 Santec IL-STS 软件 / SDK 提供,可向 Santec 或代理商索取 |
| `NationalInstruments.*.dll`、`Ivi.Visa.dll` | 安装 NI-VISA 与 NI-DAQmx 运行时(<https://www.ni.com/en/support/downloads.html>),这些程序集会注册到 .NET 的 GAC |
| `Keysight.Visa.dll` | 安装 Keysight IO Libraries Suite(<https://www.keysight.com/find/iosuite>) |
| `FTD2XX_NET.dll` | FTDI 官网 D2XX 驱动页面(<https://ftdichip.com/drivers/d2xx-drivers/>)的 .NET 封装,或使用方式 A |

使用 NI 安装包时,x64 的 `NationalInstruments.DAQmx` 应已注册到系统;加载器会按 Santec SDK 引用的完整程序集标识(`PublicKeyToken=4febd62461bf11a4`)去解析并验证实际加载的是 x64。详见 [../README.md](../README.md) 的“DAQmx `BadImageFormatException`（DLL 位数冲突）”一节。

## 版本与校验

`santec_dll/PROVENANCE.json` 记录了本项目验证过的每个 DLL 的程序集名、版本、位数、来源和 **SHA256**。获取后可核对:

```bat
:: Windows
certutil -hashfile santec_dll\STSProcess.dll SHA256
```

```bash
# macOS / Linux
shasum -a 256 santec_dll/STSProcess.dll
```

哈希不一致不一定不能用(例如 NI 的版本随安装包不同),但 `STSProcess.dll`、`Santec.Instrument.dll`、`NationalInstruments.DAQmx.dll` 的版本与位数应与清单一致:

| 文件 | 程序集版本 | 位数 |
|---|---|---|
| `STSProcess.dll` | 2.2.7.0 | x64 |
| `Santec.Instrument.dll` | 2.9.1.0 | x64 |
| `NationalInstruments.DAQmx.dll` | 17.6.45.181 | x64 |

## 自检

放好后运行:

```bat
cd windows-server
python check_setup.py
```

它会逐项检查 DLL 是否齐全、能否由 pythonnet 加载,缺什么会明确打印。

## 版权声明

这些 DLL 分别归 Santec、National Instruments、Keysight、FTDI 及其他权利人所有,不属于本项目的 MIT 许可范围。请遵守各厂商的许可协议,不要将它们提交到本仓库或任何公开位置。
