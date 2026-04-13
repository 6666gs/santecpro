"""Tests for santecpro.instruments.mpm."""

import pytest
from unittest.mock import MagicMock
from santecpro.instruments.mpm import MPMInstrument, MPM_RANGES


@pytest.fixture
def mpm(mock_resource_manager, mock_resource):
    inst = MPMInstrument(mock_resource_manager)
    inst.connect("GPIB0::17::INSTR")
    return inst


class TestMPMRanges:
    def test_mpm_ranges_constant(self):
        assert MPM_RANGES == {
            1: (-30, 10),
            2: (-40, 0),
            3: (-50, -10),
            4: (-60, -20),
            5: (-80, -30),
        }


class TestMPMConnection:
    def test_connect_sets_lf_terminator(self, mock_resource):
        rm = MagicMock()
        rm.open_resource.return_value = mock_resource
        inst = MPMInstrument(rm)
        inst.connect("GPIB0::17::INSTR")
        assert mock_resource.write_termination == "\n"
        assert mock_resource.read_termination == "\n"


class TestMPMBasicControl:
    def test_set_wavelength(self, mpm, mock_resource):
        mpm.set_wavelength(1550.0)
        mock_resource.write.assert_called_with("WAV 1550.000000")

    def test_set_range(self, mpm, mock_resource):
        mpm.set_range(2)
        mock_resource.write.assert_called_with("RANG 2")

    def test_set_range_mode_manual(self, mpm, mock_resource):
        mpm.set_range_mode("MANUAL")
        mock_resource.write.assert_called_with("RANG:MOD MANUAL")

    def test_set_range_mode_auto(self, mpm, mock_resource):
        mpm.set_range_mode("AUTO")
        mock_resource.write.assert_called_with("RANG:MOD AUTO")

    def test_set_averaging_time(self, mpm, mock_resource):
        mpm.set_averaging_time(0.00005)
        mock_resource.write.assert_called_with("AVG 0.000050")

    def test_get_averaging_time(self, mpm, mock_resource):
        mock_resource.query.return_value = "0.000050"
        assert mpm.get_averaging_time() == pytest.approx(5e-5)

    def test_set_unit(self, mpm, mock_resource):
        mpm.set_unit("dBm")
        mock_resource.write.assert_called_with("POW:UNIT dBm")

    def test_get_power(self, mpm, mock_resource):
        mock_resource.query.return_value = "-33.268"
        assert mpm.get_power(channel=1) == pytest.approx(-33.268)
        mock_resource.query.assert_called_with("READ:POW:CH1?")


class TestMPMLogging:
    def test_set_logging_data_points(self, mpm, mock_resource):
        mpm.set_logging_data_points(130001)
        mock_resource.write.assert_called_with("LOGG:POIN 130001")

    def test_start_logging(self, mpm, mock_resource):
        mpm.start_logging()
        mock_resource.write.assert_called_with("LOGG:STAT START")

    def test_stop_logging(self, mpm, mock_resource):
        mpm.stop_logging()
        mock_resource.write.assert_called_with("LOGG:STAT STOP")

    def test_get_logging_status(self, mpm, mock_resource):
        mock_resource.query.return_value = "0,50000"
        status, count = mpm.get_logging_status()
        assert status == 0
        assert count == 50000
        mock_resource.query.assert_called_with("LOGG:STAT?")

    def test_get_channel_logging_data(self, mpm, mock_resource):
        mock_resource.query.return_value = "-33.268,-33.280,-33.275"
        data = mpm.get_channel_logging_data(module=1, channel=1)
        assert len(data) == 3
        assert data[0] == pytest.approx(-33.268)
        mock_resource.query.assert_called_with("LOGG:CH1:DATA?")


class TestMPMMisc:
    def test_perform_zeroing(self, mpm, mock_resource):
        mpm.perform_zeroing()
        mock_resource.write.assert_called_with("ZERO")

    def test_set_measurement_mode(self, mpm, mock_resource):
        mpm.set_measurement_mode("SWEEP1")
        mock_resource.write.assert_called_with("MOD SWEEP1")

    def test_set_trigger_input(self, mpm, mock_resource):
        mpm.set_trigger_input("EXTERNAL")
        mock_resource.write.assert_called_with("TRIG:INP EXTERNAL")

    def test_select_optimal_range_high_power(self, mpm):
        assert mpm.select_optimal_range(5.0) == 1

    def test_select_optimal_range_medium_power(self, mpm):
        assert mpm.select_optimal_range(-25.0) == 1

    def test_select_optimal_range_low_power(self, mpm):
        assert mpm.select_optimal_range(-35.0) == 2

    def test_select_optimal_range_very_low_power(self, mpm):
        assert mpm.select_optimal_range(-55.0) == 4

    def test_select_optimal_range_ultra_low_power(self, mpm):
        assert mpm.select_optimal_range(-65.0) == 5

    def test_select_optimal_range_extremely_low_power(self, mpm):
        assert mpm.select_optimal_range(-75.0) == 5
