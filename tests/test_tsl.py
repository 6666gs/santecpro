"""Tests for santecpro.instruments.tsl."""

import struct

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

    def test_connect_uses_cr_write_and_lf_read_termination(self, mock_resource):
        rm = MagicMock()
        rm.open_resource.return_value = mock_resource
        inst = TSLInstrument(rm)
        inst.connect("GPIB0::10::INSTR")
        assert mock_resource.write_termination == "\r"
        assert mock_resource.read_termination == "\n"


class TestTSLLaserControl:
    def test_laser_on(self, tsl, mock_resource):
        tsl.laser_on()
        mock_resource.write.assert_called_with("POW:STAT 1")

    def test_laser_off(self, tsl, mock_resource):
        tsl.laser_off()
        mock_resource.write.assert_called_with("POW:STAT 0")

    def test_get_laser_status(self, tsl, mock_resource):
        mock_resource.query.return_value = "1"
        assert tsl.get_laser_status() == "1"
        mock_resource.query.assert_called_with("POW:STAT?")

    def test_shutter_open(self, tsl, mock_resource):
        tsl.shutter_open()
        mock_resource.write.assert_called_with("POW:SHUT 0")

    def test_shutter_close(self, tsl, mock_resource):
        tsl.shutter_close()
        mock_resource.write.assert_called_with("POW:SHUT 1")

    def test_get_shutter_status(self, tsl, mock_resource):
        mock_resource.query.return_value = "0"
        assert tsl.get_shutter_status() == "0"
        mock_resource.query.assert_called_with("POW:SHUT?")


class TestTSLPowerWavelength:
    def test_set_power(self, tsl, mock_resource):
        tsl.set_power(5.0)
        mock_resource.write.assert_called_with("POW:LEV 5.00")

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
        tsl.set_sweep_mode(1)
        mock_resource.write.assert_called_with("WAV:SWE:MOD 1")

    def test_set_sweep_speed(self, tsl, mock_resource):
        tsl.set_sweep_speed(50.0)
        mock_resource.write.assert_called_with("WAV:SWE:SPE 50.0")

    def test_get_sweep_speed(self, tsl, mock_resource):
        mock_resource.query.return_value = "50.000"
        assert tsl.get_sweep_speed() == 50.0

    def test_set_sweep_start(self, tsl, mock_resource):
        tsl.set_sweep_start(1500.0)
        mock_resource.write.assert_called_with("WAV:SWE:STAR 1500.000000")

    def test_set_sweep_stop(self, tsl, mock_resource):
        tsl.set_sweep_stop(1630.0)
        mock_resource.write.assert_called_with("WAV:SWE:STOP 1630.000000")

    def test_set_sweep_step(self, tsl, mock_resource):
        tsl.set_sweep_step(0.001)
        mock_resource.write.assert_called_with("WAV:SWE:STEP 0.001000")

    def test_set_sweep_step_preserves_sub_pm_resolution(self, tsl, mock_resource):
        tsl.set_sweep_step(0.00005)
        mock_resource.write.assert_called_with("WAV:SWE:STEP 0.000050")

    def test_start_sweep(self, tsl, mock_resource):
        tsl.start_sweep()
        mock_resource.write.assert_called_with("WAV:SWE 1")

    def test_stop_sweep(self, tsl, mock_resource):
        tsl.stop_sweep()
        mock_resource.write.assert_called_with("WAV:SWE 0")

    def test_pause_sweep(self, tsl, mock_resource):
        tsl.pause_sweep()
        mock_resource.write.assert_called_with("WAV:SWE 2")

    def test_restart_sweep(self, tsl, mock_resource):
        tsl.restart_sweep()
        mock_resource.write.assert_called_with("WAV:SWE 3")

    def test_get_sweep_status(self, tsl, mock_resource):
        mock_resource.query.return_value = "3"
        assert tsl.get_sweep_status() == "3"

    def test_get_sweep_mode(self, tsl, mock_resource):
        mock_resource.query.return_value = "1"
        assert tsl.get_sweep_mode() == 1
        mock_resource.query.assert_called_with("WAV:SWE:MOD?")

    def test_set_sweep_speed_rejects_too_slow(self, tsl):
        with pytest.raises(ValueError, match="below the supported minimum"):
            tsl.set_sweep_speed(0.1)

    def test_get_sweep_start_stop_step(self, tsl, mock_resource):
        mock_resource.query.side_effect = ["1540.0000", "1541.0000", "0.0010"]
        assert tsl.get_sweep_start() == pytest.approx(1540.0)
        assert tsl.get_sweep_stop() == pytest.approx(1541.0)
        assert tsl.get_sweep_step() == pytest.approx(0.001)

    def test_soft_trigger(self, tsl, mock_resource):
        tsl.soft_trigger()
        mock_resource.write.assert_called_with("WAV:SWE:SOFT")

    def test_set_trigger_output(self, tsl, mock_resource):
        tsl.set_trigger_output(3)
        mock_resource.write.assert_called_with("TRIG:OUTP 3")

    def test_set_trigger_step_width(self, tsl, mock_resource):
        tsl.set_trigger_step_width(0.01)
        mock_resource.write.assert_called_with("TRIG:OUTP:STEP 0.010000")

    def test_set_trigger_step_width_preserves_sub_pm_resolution(self, tsl, mock_resource):
        tsl.set_trigger_step_width(0.00005)
        mock_resource.write.assert_called_with("TRIG:OUTP:STEP 0.000050")

    def test_get_trigger_step_width(self, tsl, mock_resource):
        mock_resource.query.return_value = "0.0100"
        assert tsl.get_trigger_step_width() == pytest.approx(0.01)
        mock_resource.query.assert_called_with("TRIG:OUTP:STEP?")

    def test_set_scan_start_mode(self, tsl, mock_resource):
        tsl.set_scan_start_mode(1)
        mock_resource.write.assert_called_with("TRIG:INP:STAN 1")

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
        mock_resource.read_raw.return_value = b"7.58,7.59,7.60\n"
        result = tsl.get_power_monitor_data()
        assert len(result) == 3
        assert result[0] == pytest.approx(7.58)

    def test_get_power_monitor_data_binary_block(self, tsl, mock_resource):
        values = [7.58, 7.59, 7.60]
        payload = struct.pack("<3f", *values)
        block = b"#2" + str(len(payload)).encode("ascii") + payload
        mock_resource.read_raw.return_value = block

        result = tsl.get_power_monitor_data()

        mock_resource.write.assert_called_with(":READ:DAT?")
        assert result == pytest.approx(values)

    def test_configure_sweep_sets_all_params(self, tsl, mock_resource):
        tsl.configure_sweep(
            start_wl=1500.0, stop_wl=1630.0, step=0.001, speed=20.0
        )
        calls = mock_resource.write.call_args_list
        written = [c[0][0] for c in calls]
        assert "WAV:SWE:STAR 1500.000000" in written
        assert "WAV:SWE:STOP 1630.000000" in written
        assert "WAV:SWE:STEP 0.001000" in written
        assert "WAV:SWE:SPE 20.0" in written
