#!/usr/bin/env python
"""Print .NET method signatures for selected Santec DLL methods."""

from __future__ import annotations

from santec_dll_backend.loader import load_santec_dlls


def print_signature(obj: object, name: str) -> None:
    methods = obj.GetType().GetMethods()
    for method in methods:
        if method.Name != name:
            continue
        params = ", ".join(
            f"{param.ParameterType.FullName} {param.Name}" for param in method.GetParameters()
        )
        print(f"{obj.GetType().FullName}.{method.Name}({params}) -> {method.ReturnType.FullName}")


def main() -> None:
    load_santec_dlls()
    from Santec import MPM, TSL
    from Santec.STSProcess import ILSTS

    mpm = MPM()
    tsl = TSL()
    ilsts = ILSTS()
    for name in (
        "Get_216_Triggerdata",
        "Get_216_Monitordata",
        "Get_Each_Channel_Logdata",
        "Get_Each_Module_Loggdata",
        "Set_Logging_Paremeter_for_STS",
    ):
        print_signature(mpm, name)
    for name in ("Get_Logging_Data_Power_for_STS", "Set_Sweep_Parameter_for_STS"):
        print_signature(tsl, name)
    for name in (
        "Add_Ref_MPMData_CH",
        "Add_Ref_MonitorData",
        "Add_Ref_Rawdata",
        "Add_Ref_Power_Rawdata",
        "Set_Ref_MonitorData",
        "Cal_RefData_Rescaling",
        "Cal_RefData_Rescaling_TSLMonitor",
        "Get_Ref_RawData",
        "Get_Ref_Power_Rawdata",
        "Get_Ref_Monitor_Rawdata",
        "Get_Target_Wavelength_Table",
    ):
        print_signature(ilsts, name)


if __name__ == "__main__":
    main()
