# Vendor DLLs

The Windows backend depends on proprietary Santec/NI/Keysight DLLs, loaded from
`vendor/santec_dll/`:

```
vendor/santec_dll/
├── STSProcess.dll            (Santec IL-STS SDK)
├── Santec.Instrument.dll     (Santec instrument SDK)
├── FTD2XX_NET.dll            (FTDI D2XX)
├── Ivi.Visa.dll
├── Keysight.Visa.dll         (Keysight IO Libraries)
└── NationalInstruments.*.dll (NI-VISA / NI-DAQmx runtime)
```

**These DLLs are bundled in this repository** (in `santec_dll/`) so the server is
install-and-run — no manual sourcing needed. `loader.py` reads them from this
directory by default.

> ⚠️ **Proprietary — do not redistribute publicly.** They are the property of
> Santec, National Instruments, and Keysight and are included here only because
> this repository is **private**. Do not make this repository public or copy the
> DLLs into any public location. To re-source them, they ship with the vendor
> installers on the measurement PC (Santec IL-STS SDK, NI-VISA/DAQmx, Keysight IO).
