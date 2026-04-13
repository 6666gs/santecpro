"""Tests for santecpro.instruments.tsl."""

import pytest
from unittest.mock import MagicMock, call
from santecpro.instruments.tsl import TSLInstrument
from santecpro.exceptions import InstrumentConnectionError


@pytest.fixture
def tsl(mock_resource_manager, mock_resource):
    inst = TSLInstrument(mock_resource_manager)
    inst.connect("GPIB0::10::INSTR")
    return inst


class TestTSLConnection:
    def test_connect_sends_init_sequence(self, mock_resource):
        rm = MagicMock()
        rm.open_resource.return_value = mock_resource
        inst = TSLInstrument(rm)
        inst.connect("GPIB0::10::INSTR")
        mock_resource.write.assert_any_call("*CLS")
        mock_resource.write.assert_any_call("*RST")


class TestTSLLaserControl:
    def test_laser_on(self, tsl, mock_resource):
        tsl.laser_on()
        mock_resource.write.assert_called_with("LD:STAT ON")

    def test_laser_off(self, tsl, mock_resource):
        tsl.laser_off()
        mock_resource.write.assert_called_with("LD:STAT OFF")

    def test_get_laser_status(self, tsl, mock_resource):
        mock_resource.query.return_value = "ON"
        assert tsl.get_laser_status() == "ON"
        mock_resource.query.assert_called_with("LD:STAT?")

    def test_shutter_open(self, tsl, mock_resource):
        tsl.shutter_open()
        mock_resource.write.assert_called_with("SHUT ON")

    def test_shutter_close(self, tsl, mock_resource):
        tsl.shutter_close()
        mock_resource.write.assert_called_with("SHUT OFF")

    def test_get_shutter_status(self, tsl, mock_resource):
        mock_resource.query.return_value = "OPEN"
        assert tsl.get_shutter_status() == "OPEN"
        mock_resource.query.assert_called_with("SHUT?")


class TestTSLPowerWavelength:
    def test_set_power(self, tsl, mock_resource):
        tsl.set_power(5.0)
        mock_resource.write.assert_called_with("POW:LEV 5.000000")

    def test_get_power(self, tsl, mock_resource):
        mock_resource.query.return_value = "5.000"
        assert tsl.get_power() == 5.0
        mock_resource.query.assert_called_with("POW:LEV?")

    def test_set_wavelength(self, tsl, mock_resource):
        tsl.set_wavelength(1550.0)
        mock_resource.write.assert_called_with("WAV 1550.000000")

    def test_get_wavelength(self, tsl, mock_resource):
        mock_resource.query.return_value = "1550.000"
        assert tsl.get_wavelength() == 1550.0
        mock_resource.query.assert_called_with("WAV?")


class TestTSLSweep:
    def test_set_sweep_mode(self, tsl, mock_resource):
        tsl.set_sweep_mode("CONT_ONEWAY")
        mock_resource.write.assert_called_with("SWEEP:MODE CONT_ONEWAY")

    def test_set_sweep_speed(self, tsl, mock_resource):
        tsl.set_sweep_speed(50.0)
        mock_resource.write.assert_called_with("SWEEP:SPED 50.000000")

    def test_get_sweep_speed(self, tsl, mock_resource):
        mock_resource.query.return_value = "50.000"
        assert tsl.get_sweep_speed() == 50.0

    def test_set_sweep_start(self, tsl, mock_resource):
        tsl.set_sweep_start(1500.0)
        mock_resource.write.assert_called_with("SWEEP:STAR:WAV 1500.000000")

    def test_set_sweep_stop(self, tsl, mock_resource):
        tsl.set_sweep_stop(1630.0)
        mock_resource.write.assert_called_with("SWEEP:STOP:WAV 1630.000000")

    def test_set_sweep_step(self, tsl, mock_resource):
        tsl.set_sweep_step(0.001)
        mock_resource.write.assert_called_with("SWEEP:STEP 0.001000")

    def test_start_sweep(self, tsl, mock_resource):
        tsl.start_sweep()
        mock_resource.write.assert_called_with("SWEEP:STAT START")

    def test_stop_sweep(self, tsl, mock_resource):
        tsl.stop_sweep()
        mock_resource.write.assert_called_with("SWEEP:STAT STOP")

    def test_pause_sweep(self, tsl, mock_resource):
        tsl.pause_sweep()
        mock_resource.write.assert_called_with("SWEEP:STAT PAUSE")

    def test_restart_sweep(self, tsl, mock_resource):
        tsl.restart_sweep()
        mock_resource.write.assert_called_with("SWEEP:STAT REST")

    def test_get_sweep_status(self, tsl, mock_resource):
        mock_resource.query.return_value = "STANDBY"
        assert tsl.get_sweep_status() == "STANDBY"

    def test_soft_trigger(self, tsl, mock_resource):
        tsl.soft_trigger()
        mock_resource.write.assert_called_with("TRIG:SOFT")

    def test_set_trigger_output(self, tsl, mock_resource):
        tsl.set_trigger_output("STEP")
        mock_resource.write.assert_called_with("TRIG:OUTP STEP")

    def test_set_scan_start_mode(self, tsl, mock_resource):
        tsl.set_scan_start_mode("WAITING_FOR_TRIGGER")
        mock_resource.write.assert_called_with("SWEEP:STAR:MOD WAITING_FOR_TRIGGER")

    def test_status_clear(self, tsl, mock_resource):
        tsl.status_clear()
        mock_resource.write.assert_called_with("*CLS")

    def test_device_reset(self, tsl, mock_resource):
        tsl.device_reset()
        mock_resource.write.assert_called_with("*RST")

    def test_get_logging_data_points(self, tsl, mock_resource):
        mock_resource.query.return_value = "1000"
        assert tsl.get_logging_data_points() == 1000
        mock_resource.query.assert_called_with(":READ:POIN?")

    def test_get_power_monitor_data(self, tsl, mock_resource):
        mock_resource.query.return_value = "7.58,7.59,7.60"
        result = tsl.get_power_monitor_data()
        assert len(result) == 3
        assert result[0] == pytest.approx(7.58)

    def test_configure_sweep_sets_all_params(self, tsl, mock_resource):
        tsl.configure_sweep(
            start_wl=1500.0, stop_wl=1630.0, step=0.001, speed=20.0
        )
        calls = mock_resource.write.call_args_list
        written = [c[0][0] for c in calls]
        assert "SWEEP:STAR:WAV 1500.000000" in written
        assert "SWEEP:STOP:WAV 1630.000000" in written
        assert "SWEEP:STEP 0.001000" in written
        assert "SWEEP:SPED 20.000000" in written
