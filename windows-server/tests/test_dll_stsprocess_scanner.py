"""Tests for the Windows DLL/STSProcess scan coordinator."""

from __future__ import annotations

import pytest

from santec_dll_backend.scanner import STSScanSettings, run_stsprocess_scan


class FakeTsl:
    def __init__(self) -> None:
        self.connected = False
        self.disconnected = False

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.disconnected = True

    def idn(self) -> str:
        return "TSL"

    def set_sts_sweep_parameters(self, start: float, stop: float, speed: float, step: float) -> float:
        return 0.001

    def set_power_dbm(self, power: float) -> None:
        self.power = power

    def set_continuous_oneway_sweep_mode(self) -> None:
        pass

    def set_waiting_for_trigger_start_mode(self) -> None:
        pass

    def start_sweep(self) -> None:
        pass

    def stop_sweep(self, raise_on_error: bool = True) -> None:
        pass

    def soft_trigger(self) -> None:
        pass

    def wait_for_status(self, timeout_ms: int, status_name: str) -> None:
        pass

    def get_sts_power_monitor_data(self, speed: float, actual_step: float) -> list[float]:
        raise RuntimeError("monitor unavailable")


class FakeMpm:
    def __init__(self) -> None:
        self.connected = False
        self.disconnected = False

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.disconnected = True

    def idn(self) -> str:
        return "MPM"

    def set_sts_logging_parameters(
        self, start: float, stop: float, step: float, actual_step: float, speed: float
    ) -> None:
        pass

    def configure_power_logging(self, module: int, channel: int, mpm_range: int) -> None:
        self.configured_power_logging = getattr(self, "configured_power_logging", [])
        self.configured_power_logging.append((module, channel, mpm_range))

    def get_logging_data_point(self) -> int:
        return 1006

    def start_logging(self) -> None:
        pass

    def stop_logging(self, raise_on_error: bool = True) -> None:
        pass

    def wait_for_log_completion(self) -> tuple[int, int]:
        return 1, 1006

    def get_channel_log_data(self, module: int, channel: int) -> list[float]:
        return [float(i + channel * 10000) for i in range(1006)]

    def get_trigger_data(self, module: int) -> list[float]:
        raise RuntimeError("trigger unavailable")

    def get_216_monitor_data(self, module: int) -> tuple[list[float], list[float]]:
        raise RuntimeError("216 monitor unavailable")


class FakeSts:
    def __init__(self) -> None:
        self.added_reference_data = []

    def make_wavelength_tables(self, start: float, stop: float, step: float, actual_step: float) -> None:
        self.target = [start + i * step for i in range(1001)]

    def get_target_wavelength_table(self) -> list[float]:
        return self.target

    def make_data_struct(self, module: int, channel: int, mpm_range: int = 1, sweep_count: int = 1):
        return object()

    def set_tsl_monitor_rescaling(self, averaging_time_ms: float = 0.01) -> None:
        pass

    def add_reference_data(self, powers, trigger, monitor, data_struct) -> None:
        self.added_reference_data.append(list(powers))
        assert len(powers) == 1006
        assert trigger[0] == 0.0
        assert trigger[-1] == 1005.0
        assert len(monitor) == 1006

    def rescale_reference(self, data_struct):
        return self.target, [-float(len(self.added_reference_data))] * 1001, [0.0] * 1001


def test_run_stsprocess_scan_rescales_raw_points_to_target_points(tmp_path):
    settings = STSScanSettings(
        start_wl=1540.0,
        stop_wl=1540.1,
        step=0.0001,
        speed=1.0,
        power=0.0,
        csv_path=tmp_path / "scan.csv",
    )
    tsl = FakeTsl()
    mpm = FakeMpm()

    result = run_stsprocess_scan(settings, tsl=tsl, mpm=mpm, sts=FakeSts())

    assert len(result.wavelengths) == 1001
    assert len(result.powers) == 1001
    assert result.raw_points == 1006
    assert result.target_points == 1001
    assert result.actual_step == pytest.approx(0.001)
    assert settings.csv_path.exists()
    assert tsl.power == pytest.approx(0.0)
    assert mpm.configured_power_logging == [(0, 1, 1)]


def test_run_stsprocess_scan_returns_selected_channels(tmp_path):
    settings = STSScanSettings(
        start_wl=1540.0,
        stop_wl=1540.1,
        step=0.0001,
        speed=1.0,
        power=0.0,
        mpm_channels=(1, 2, 4),
        csv_path=tmp_path / "scan.csv",
    )
    mpm = FakeMpm()

    result = run_stsprocess_scan(settings, tsl=FakeTsl(), mpm=mpm, sts=FakeSts())

    assert sorted(result.channel_powers) == [1, 2, 4]
    assert len(result.channel_powers[2]) == 1001
    assert result.powers == result.channel_powers[1]
    assert mpm.configured_power_logging == [(0, 1, 1), (0, 2, 1), (0, 4, 1)]
