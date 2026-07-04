"""Tests for santecpro.instruments.mpm."""

import struct
import pytest
from unittest.mock import MagicMock
from santecpro.instruments.mpm import MPMInstrument, MPM_RANGES
from santecpro.exceptions import InstrumentOperationError


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
        assert mock_resource.timeout == 5000


class TestMPMBasicControl:
    def test_set_wavelength(self, mpm, mock_resource):
        mpm.set_wavelength(1550.0)
        mock_resource.write.assert_called_with("WAV 1550.000000")

    def test_set_range(self, mpm, mock_resource):
        mpm.set_range(2)
        mock_resource.write.assert_called_with("LEV 2")

    def test_get_range(self, mpm, mock_resource):
        mock_resource.query.return_value = "3"
        assert mpm.get_range() == 3
        mock_resource.query.assert_called_with("LEV?")

    def test_set_range_mode_manual(self, mpm, mock_resource):
        mpm.set_range_mode(0)
        mock_resource.write.assert_called_with("AUTO 0")

    def test_set_range_mode_auto(self, mpm, mock_resource):
        mpm.set_range_mode(1)
        mock_resource.write.assert_called_with("AUTO 1")

    def test_get_range_mode(self, mpm, mock_resource):
        mock_resource.query.return_value = "1"
        assert mpm.get_range_mode() == 1
        mock_resource.query.assert_called_with("AUTO?")

    def test_set_averaging_time(self, mpm, mock_resource):
        mpm.set_averaging_time(0.00005)
        mock_resource.write.assert_called_with("AVG 0.00")

    def test_get_averaging_time(self, mpm, mock_resource):
        mock_resource.query.return_value = "0.000050"
        assert mpm.get_averaging_time() == pytest.approx(5e-5)

    def test_set_unit_dbm(self, mpm, mock_resource):
        mpm.set_unit(0)
        mock_resource.write.assert_called_with("UNIT 0")

    def test_set_unit_mw(self, mpm, mock_resource):
        mpm.set_unit(1)
        mock_resource.write.assert_called_with("UNIT 1")

    def test_get_unit(self, mpm, mock_resource):
        mock_resource.query.return_value = "0"
        assert mpm.get_unit() == 0
        mock_resource.query.assert_called_with("UNIT?")

    def test_get_power_all_ports(self, mpm, mock_resource):
        mock_resource.query.return_value = "-33.268,-33.280,-33.275,-33.290"
        powers = mpm.get_power(module=0)
        assert len(powers) == 4
        assert powers[0] == pytest.approx(-33.268)
        mock_resource.query.assert_called_with("READ? 0")

    def test_get_power_channel(self, mpm, mock_resource):
        mock_resource.query.return_value = "-33.268,-33.280,-33.275,-33.290"
        power = mpm.get_power_channel(module=0, channel=2)
        assert power == pytest.approx(-33.280)


class TestMPMSweepConfig:
    def test_set_measurement_mode(self, mpm, mock_resource):
        mpm.set_measurement_mode("SWEEP1")
        mock_resource.write.assert_called_with("WMOD SWEEP1")

    def test_get_measurement_mode(self, mpm, mock_resource):
        mock_resource.query.return_value = "SWEEP1"
        assert mpm.get_measurement_mode() == "SWEEP1"
        mock_resource.query.assert_called_with("WMOD?")

    def test_set_sweep_wavelength(self, mpm, mock_resource):
        mpm.set_sweep_wavelength(1500.0, 1600.0, 0.01)
        mock_resource.write.assert_called_with("WSET 1500.000000,1600.000000,0.010000")

    def test_set_sweep_wavelength_preserves_sub_pm_step(self, mpm, mock_resource):
        mpm.set_sweep_wavelength(1540.0, 1541.0, 0.00005)
        mock_resource.write.assert_called_with("WSET 1540.000000,1541.000000,0.000050")

    def test_get_sweep_wavelength(self, mpm, mock_resource):
        mock_resource.query.return_value = "1500.000,1600.000,0.010"
        start, stop, step = mpm.get_sweep_wavelength()
        assert start == pytest.approx(1500.0)
        assert stop == pytest.approx(1600.0)
        assert step == pytest.approx(0.01)
        mock_resource.query.assert_called_with("WSET?")

    def test_set_sweep_speed(self, mpm, mock_resource):
        mpm.set_sweep_speed(50.0)
        mock_resource.write.assert_called_with("SPE 50.000")

    def test_get_sweep_speed(self, mpm, mock_resource):
        mock_resource.query.return_value = "50.000"
        assert mpm.get_sweep_speed() == pytest.approx(50.0)
        mock_resource.query.assert_called_with("SPE?")

    def test_set_trigger_input(self, mpm, mock_resource):
        mpm.set_trigger_input(1)
        mock_resource.write.assert_called_with("TRIG 1")

    def test_get_trigger_input(self, mpm, mock_resource):
        mock_resource.query.return_value = "1"
        assert mpm.get_trigger_input() == 1
        mock_resource.query.assert_called_with("TRIG?")


class TestMPMLogging:
    def test_set_logging_data_points(self, mpm, mock_resource):
        mpm.set_logging_data_points(130001)
        mock_resource.write.assert_called_with("LOGN 130001")

    def test_get_logging_data_points(self, mpm, mock_resource):
        mock_resource.query.return_value = "130001"
        assert mpm.get_logging_data_points() == 130001
        mock_resource.query.assert_called_with("LOGN?")

    def test_start_logging(self, mpm, mock_resource):
        mpm.start_logging()
        mock_resource.write.assert_called_with("MEAS")

    def test_stop_logging(self, mpm, mock_resource):
        mpm.stop_logging()
        mock_resource.write.assert_called_with("STOP")

    def test_get_logging_status(self, mpm, mock_resource):
        mock_resource.query.return_value = "0,50000"
        status, count = mpm.get_logging_status()
        assert status == 0
        assert count == 50000
        mock_resource.query.assert_called_with("STAT?")

    def test_get_error(self, mpm, mock_resource):
        mock_resource.query.return_value = "104,uPP Comm. Moduel Mismatched"
        code, message = mpm.get_error()
        assert code == 104
        assert message == "uPP Comm. Moduel Mismatched"
        mock_resource.query.assert_called_with("ERR?")

    @pytest.mark.parametrize("response", ["0", "0,No error", "0,No Error"])
    def test_assert_no_error_accepts_clear_error(self, mpm, mock_resource, response):
        mock_resource.query.return_value = response
        mpm.assert_no_error()

    def test_assert_no_error_raises_for_mpm_error(self, mpm, mock_resource):
        mock_resource.query.return_value = "104,uPP Comm. Moduel Mismatched"
        with pytest.raises(InstrumentOperationError, match="MPM error 104"):
            mpm.assert_no_error()

    def test_get_channel_logging_data_binary(self, mpm, mock_resource):
        """Test binary LOGG? response parsing."""
        # Build a fake IEEE 488.2 binary block with 3 floats
        floats = [-33.268, -33.280, -33.275]
        binary_data = struct.pack("<3f", *floats)
        # Format: #<digits_count><byte_count><data>
        byte_count_str = str(len(binary_data))
        header = f"#{len(byte_count_str)}{byte_count_str}".encode()
        mock_resource.read_raw.return_value = header + binary_data

        data = mpm.get_channel_logging_data(module=0, channel=1)
        assert len(data) == 3
        assert data[0] == pytest.approx(-33.268, abs=0.01)
        assert data[1] == pytest.approx(-33.280, abs=0.01)

    def test_get_channel_logging_data_ascii_fallback(self, mpm, mock_resource):
        """Test ASCII fallback for non-binary LOGG? response."""
        mock_resource.read_raw.return_value = b"-33.268,-33.280,-33.275"
        data = mpm.get_channel_logging_data(module=0, channel=1)
        assert len(data) == 3
        assert data[0] == pytest.approx(-33.268)

    def test_get_module_logging_data(self, mpm, mock_resource):
        """get_module_logging_data queries all 4 channels."""
        floats = [-10.0, -11.0]
        binary_data = struct.pack("<2f", *floats)
        byte_count_str = str(len(binary_data))
        header = f"#{len(byte_count_str)}{byte_count_str}".encode()
        mock_resource.read_raw.return_value = header + binary_data

        result = mpm.get_module_logging_data(module=0)
        assert len(result) == 4  # 4 channels
        assert len(result[0]) == 2


class TestMPMMisc:
    def test_perform_zeroing(self, mpm, mock_resource):
        mpm.perform_zeroing()
        mock_resource.write.assert_called_with("ZERO")

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
