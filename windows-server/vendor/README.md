# Vendor DLLs

The Windows backend depends on proprietary DLLs that are **not** redistributed in
this repository for licensing reasons:

```
vendor/santec_dll/
├── STSProcess.dll
├── Santec.Instrument.dll
├── FTD2XX_NET.dll
├── Ivi.Visa.dll
├── Keysight.Visa.dll
└── NationalInstruments.*.dll
```

Obtain these from the corresponding vendor installers on the Windows measurement PC:

- **STSProcess.dll / Santec.Instrument.dll** — Santec IL-STS / instrument SDK
- **NationalInstruments.\*.dll** — NI-VISA / NI-DAQmx runtime
- **Keysight.Visa.dll / Ivi.Visa.dll** — Keysight IO Libraries Suite
- **FTD2XX_NET.dll** — FTDI D2XX drivers

Place them under `vendor/santec_dll/` before running the Windows server.
