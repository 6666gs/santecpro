"""Thin wrappers around the official Santec Instrument DLL."""

from __future__ import annotations

from dataclasses import dataclass
import time

from .loader import load_santec_dlls


from santecpro.exceptions import ScanCancelled


def check_cancelled(cancel_event=None):
    if cancel_event is not None and cancel_event.is_set():
        raise ScanCancelled("Scan cancelled")


@dataclass(frozen=True)
class GpibAddress:
    board: int
    address: int


def parse_gpib_resource(resource: str) -> GpibAddress:
    """Parse resources like ``GPIB3::1::INSTR``."""
    parts = resource.upper().split("::")
    if len(parts) < 2 or not parts[0].startswith("GPIB"):
        raise ValueError(f"Expected a GPIB resource, got {resource!r}")
    return GpibAddress(board=int(parts[0][4:]), address=int(parts[1]))


def instrument_error_string(code: int) -> str:
    try:
        from Santec import ErrorString

        return str(ErrorString.GetErrorString(code))
    except Exception:
        return str(code)


def raise_if_error(code: int, action: str) -> None:
    if int(code) != 0:
        raise RuntimeError(f"{action} failed with code {code}: {instrument_error_string(code)}")


class DllTsl:
    def __init__(self, resource: str, gpib_type: str = "ni") -> None:
        load_santec_dlls()
        from Santec import TSL, CommunicationTerminator
        from Santec.Communication import GPIBConnectType

        gpib = parse_gpib_resource(resource)
        self._tsl = TSL()
        self._tsl.Terminator = CommunicationTerminator.Cr
        self._tsl.GPIBBoard = gpib.board
        self._tsl.GPIBAddress = gpib.address
        self._tsl.GPIBConnectType = (
            GPIBConnectType.NI4882
            if gpib_type.lower() == "ni"
            else GPIBConnectType.KeysightIO
        )

    def connect(self) -> None:
        from Santec.Communication import CommunicationMethod

        raise_if_error(self._tsl.Connect(CommunicationMethod.GPIB), "TSL connect")

    def disconnect(self) -> None:
        self._tsl.DisConnect()

    def idn(self) -> str:
        code, response = self._tsl.Echo("*IDN?", "")
        raise_if_error(code, "TSL *IDN?")
        return str(response)

    def set_power_dbm(self, power_dbm: float) -> None:
        try:
            raise_if_error(
                self._tsl.Set_Power_Unit(self._tsl.Power_Unit.dBm),
                "TSL Set_Power_Unit dBm",
            )
        except AttributeError:
            pass
        try:
            raise_if_error(
                self._tsl.Set_Power_Mode(self._tsl.Power_Mode.APC),
                "TSL Set_Power_Mode APC",
            )
        except AttributeError:
            pass
        raise_if_error(
            self._tsl.Set_APC_Power_dBm(power_dbm),
            "TSL Set_APC_Power_dBm",
        )

    def laser_on(self) -> None:
        raise_if_error(
            self._tsl.Set_LD_Status(self._tsl.LD_Status.LD_ON),
            "TSL Set_LD_Status ON",
        )

    def laser_is_on(self) -> bool:
        """Read actual LD state; setting LD_ON alone does not mean warmup finished."""
        code, status = self._tsl.Get_LD_Status(self._tsl.LD_Status.LD_OFF)
        raise_if_error(code, "TSL Get_LD_Status")
        return status == self._tsl.LD_Status.LD_ON

    def laser_off(self) -> None:
        raise_if_error(
            self._tsl.Set_LD_Status(self._tsl.LD_Status.LD_OFF),
            "TSL Set_LD_Status OFF",
        )

    def shutter_open(self) -> None:
        raise_if_error(
            self._tsl.Set_Shutter_Status(self._tsl.Shutter_Status.Shutter_Open),
            "TSL Set_Shutter_Status Open",
        )

    def shutter_close(self) -> None:
        raise_if_error(
            self._tsl.Set_Shutter_Status(self._tsl.Shutter_Status.Shutter_Close),
            "TSL Set_Shutter_Status Close",
        )

    def set_sts_sweep_parameters(
        self, start_nm: float, stop_nm: float, speed_nm_s: float, step_nm: float
    ) -> float:
        code, actual_step = self._tsl.Set_Sweep_Parameter_for_STS(
            start_nm, stop_nm, speed_nm_s, step_nm, 0
        )
        raise_if_error(code, "TSL Set_Sweep_Parameter_for_STS")
        return float(actual_step)

    def set_waiting_for_trigger_start_mode(self) -> None:
        raise_if_error(
            self._tsl.Set_Sweep_Start_Mode(self._tsl.Sweep_Start_Mode.WaitingforTrigger),
            "TSL Set_Sweep_Start_Mode WaitingforTrigger",
        )

    def set_continuous_oneway_sweep_mode(self) -> None:
        raise_if_error(
            self._tsl.Set_Sweep_Mode(self._tsl.Sweep_Mode.Continuous_Oneway),
            "TSL Set_Sweep_Mode Continuous_Oneway",
        )

    def start_sweep(self) -> None:
        raise_if_error(self._tsl.Sweep_Start(), "TSL Sweep_Start")

    def stop_sweep(self, raise_on_error: bool = True) -> None:
        code = self._tsl.Sweep_Stop()
        if raise_on_error:
            raise_if_error(code, "TSL Sweep_Stop")

    def soft_trigger(self) -> None:
        raise_if_error(self._tsl.Set_Software_Trigger(), "TSL Set_Software_Trigger")

    def wait_for_status(self, timeout_ms: int, status_name: str, cancel_event=None) -> None:
        statuses = {
            "standby": self._tsl.Sweep_Status.Standby,
            "running": self._tsl.Sweep_Status.Running,
            "pause": self._tsl.Sweep_Status.Pausing,
            "waiting_for_trigger": self._tsl.Sweep_Status.WaitingforTrigger,
            "returning": self._tsl.Sweep_Status.Returning,
        }
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            check_cancelled(cancel_event)
            code, status = self._tsl.Get_Sweep_Status(self._tsl.Sweep_Status.Standby)
            raise_if_error(code, "TSL Get_Sweep_Status")
            if status == statuses[status_name]:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError(f"TSL did not reach {status_name} within {timeout_ms} ms")
            if cancel_event is not None:
                cancel_event.wait(0.05)
            else:
                time.sleep(0.05)

    def get_sts_power_monitor_data(
        self, speed_nm_s: float, actual_step_nm: float
    ) -> list[float]:
        code, _count, monitor = self._tsl.Get_Logging_Data_Power_for_STS(
            speed_nm_s, actual_step_nm, 0, None
        )
        if int(code) not in (0, -2):
            raise_if_error(code, "TSL Get_Logging_Data_Power_for_STS")
        return list(monitor)


class DllMpm:
    def __init__(self, resource: str, gpib_type: str = "ni") -> None:
        load_santec_dlls()
        from Santec import MPM, CommunicationTerminator
        from Santec.Communication import GPIBConnectType

        gpib = parse_gpib_resource(resource)
        self._mpm = MPM()
        self._mpm.Terminator = CommunicationTerminator.Lf
        self._mpm.GPIBBoard = gpib.board
        self._mpm.GPIBAddress = gpib.address
        self._mpm.GPIBConnectType = (
            GPIBConnectType.NI4882
            if gpib_type.lower() == "ni"
            else GPIBConnectType.KeysightIO
        )

    def connect(self) -> None:
        from Santec.Communication import CommunicationMethod

        raise_if_error(self._mpm.Connect(CommunicationMethod.GPIB), "MPM connect")

    def disconnect(self) -> None:
        self._mpm.DisConnect()

    def idn(self) -> str:
        code, response = self._mpm.Echo("*IDN?", "")
        raise_if_error(code, "MPM *IDN?")
        return str(response)

    def configure_power_logging(self, module: int, channel: int, mpm_range: int) -> None:
        raise_if_error(
            self._mpm.Set_Unit(self._mpm.Power_Unit.dBm),
            "MPM Set_Unit dBm",
        )
        raise_if_error(
            self._mpm.Set_READ_Range_Mode(self._mpm.READ_Range_Mode.Manual),
            "MPM Set_READ_Range_Mode Manual",
        )
        raise_if_error(self._mpm.Set_Range(mpm_range), "MPM Set_Range")
        try:
            raise_if_error(
                self._mpm.Set_Range_Each_Channel(module, channel, mpm_range),
                "MPM Set_Range_Each_Channel",
            )
        except RuntimeError:
            # Some modules apply Set_Range globally for the active logging mode.
            pass

    def read_power_channel(self, module: int, channel: int) -> float:
        code, power = self._mpm.Get_READ_Power_Channel(module, channel, 0)
        raise_if_error(code, "MPM Get_READ_Power_Channel")
        return float(power)

    def read_power_channels(self, module: int, channels: list[int] | tuple[int, ...]) -> dict[int, float]:
        return {int(channel): self.read_power_channel(module, int(channel)) for channel in channels}

    def set_sts_logging_parameters(
        self,
        start_nm: float,
        stop_nm: float,
        step_nm: float,
        actual_trigger_step_nm: float,
        speed_nm_s: float,
    ) -> None:
        code = self._mpm.Set_Logging_Paremeter_for_STS(
            start_nm,
            stop_nm,
            step_nm,
            actual_trigger_step_nm,
            speed_nm_s,
            self._mpm.Measurement_Mode.Freerun,
        )
        raise_if_error(code, "MPM Set_Logging_Paremeter_for_STS")

    def start_logging(self) -> None:
        raise_if_error(self._mpm.Logging_Start(), "MPM Logging_Start")

    def stop_logging(self, raise_on_error: bool = True) -> None:
        code = self._mpm.Logging_Stop()
        if raise_on_error:
            raise_if_error(code, "MPM Logging_Stop")

    def wait_for_log_completion(self, expected_points=None, timeout_s=10, cancel_event=None) -> tuple[int, int]:
        deadline = time.monotonic() + timeout_s
        while True:
            check_cancelled(cancel_event)
            code, status, logging_point = self._mpm.Get_Logging_Status(0, 0)
            if int(code) == -999:
                raise RuntimeError("MPM trigger error; check trigger cable connection.")
            raise_if_error(code, "MPM Get_Logging_Status")
            if expected_points is None or int(logging_point) >= expected_points:
                return int(status), int(logging_point)
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Incomplete MPM logging: {logging_point}/{expected_points} points")
            if cancel_event is not None:
                cancel_event.wait(0.05)
            else:
                time.sleep(0.05)

    def get_logging_data_point(self) -> int:
        code, count = self._mpm.Get_Logging_Data_Point(0)
        raise_if_error(code, "MPM Get_Logging_Data_Point")
        return int(count)

    def get_channel_log_data(self, module: int, channel: int) -> list[float]:
        code, data = self._mpm.Get_Each_Channel_Logdata(module, channel, None)
        raise_if_error(code, "MPM Get_Each_Channel_Logdata")
        return list(data)

    def get_trigger_data(self, module: int) -> list[float]:
        code, trigger = self._mpm.Get_216_Triggerdata(module, None)
        raise_if_error(code, "MPM Get_216_Triggerdata")
        return list(trigger)

    def get_216_monitor_data(self, module: int) -> tuple[list[float], list[float]]:
        code, trigger, monitor = self._mpm.Get_216_Monitordata(module, None, None)
        raise_if_error(code, "MPM Get_216_Monitordata")
        return list(trigger), list(monitor)


class DllStsProcess:
    def __init__(self) -> None:
        load_santec_dlls()
        from Santec.STSProcess import ILSTS

        self._ilsts = ILSTS()

    def make_wavelength_tables(
        self,
        start_nm: float,
        stop_nm: float,
        requested_step_nm: float,
        actual_step_nm: float,
    ) -> None:
        raise_if_error(
            self._ilsts.Make_Sweep_Wavelength_Table(start_nm, stop_nm, actual_step_nm),
            "STS Make_Sweep_Wavelength_Table",
        )
        raise_if_error(
            self._ilsts.Make_Target_Wavelength_Table(start_nm, stop_nm, requested_step_nm),
            "STS Make_Target_Wavelength_Table",
        )

    def set_tsl_monitor_rescaling(self, averaging_time_ms: float = 0.01) -> None:
        from Santec.STSProcess import RescalingMode

        raise_if_error(
            self._ilsts.Set_Rescaling_Setting(
                RescalingMode.Freerun_TSLMonitor,
                averaging_time_ms,
                True,
            ),
            "STS Set_Rescaling_Setting",
        )

    def make_data_struct(
        self,
        module: int,
        channel: int,
        mpm_range: int = 1,
        sweep_count: int = 1,
    ):
        from Santec.STSProcess import STSDataStruct

        data = STSDataStruct()
        data.MPMNumber = 0
        data.SlotNumber = int(module)
        data.ChannelNumber = int(channel)
        data.RangeNumber = int(mpm_range)
        data.SweepCount = int(sweep_count)
        data.SOP = 0
        return data

    def add_reference_data(
        self,
        powers: list[float],
        trigger: list[float],
        monitor: list[float],
        data_struct,
    ) -> None:
        raise_if_error(
            self._ilsts.Add_Ref_MPMData_CH(powers, data_struct),
            "STS Add_Ref_MPMData_CH",
        )
        raise_if_error(
            self._ilsts.Add_Ref_MonitorData(trigger, monitor, data_struct),
            "STS Add_Ref_MonitorData",
        )

    def add_reference_rawdata(
        self,
        powers: list[float],
        monitor: list[float],
        data_struct,
    ) -> None:
        raise_if_error(
            self._ilsts.Add_Ref_Rawdata(powers, monitor, data_struct),
            "STS Add_Ref_Rawdata",
        )

    def add_reference_power_rawdata(self, powers: list[float], data_struct) -> None:
        raise_if_error(
            self._ilsts.Add_Ref_Power_Rawdata(powers, data_struct),
            "STS Add_Ref_Power_Rawdata",
        )

    def rescale_reference(self, data_struct) -> tuple[list[float], list[float], list[float]]:
        raise_if_error(self._ilsts.Cal_RefData_Rescaling(), "STS Cal_RefData_Rescaling")
        code, rescaled_power, rescaled_monitor = self._ilsts.Get_Ref_RawData(
            data_struct, None, None
        )
        raise_if_error(code, "STS Get_Ref_RawData")
        code, wavelength = self._ilsts.Get_Target_Wavelength_Table(None)
        raise_if_error(code, "STS Get_Target_Wavelength_Table")
        return list(wavelength), list(rescaled_power), list(rescaled_monitor)

    def get_target_wavelength_table(self) -> list[float]:
        code, wavelength = self._ilsts.Get_Target_Wavelength_Table(None)
        raise_if_error(code, "STS Get_Target_Wavelength_Table")
        return list(wavelength)
