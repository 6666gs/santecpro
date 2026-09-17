"""Tests for santecpro.exporter."""

import csv
import os
import tempfile

import numpy as np
import pytest

from santecpro.results import ScanResult, ILMeasurement
from santecpro.exporter import save_raw_csv, save_loss_csv


TSL_IDN = "SANTEC,TSL-550,12345,1.00"
MPM_IDN = "SANTEC,MPM-210,67890,2.00"


def _make_scan_result() -> ScanResult:
    return ScanResult(
        wavelengths=np.array([1500.0, 1500.001, 1500.002]),
        powers=np.array([-33.268, -33.280, -33.275]),
        monitor_powers=np.array([7.58, 7.59, 7.60]),
        scan_params={
            "start_wl": 1500.0,
            "stop_wl": 1630.0,
            "step": 0.001,
            "speed": 20.0,
            "power": 0.0,
        },
        timestamp="2026-04-13T10:30:00",
        mpm_range=1,
    )


def _make_il_measurement() -> ILMeasurement:
    ref = _make_scan_result()
    meas = ScanResult(
        wavelengths=np.array([1500.0, 1500.001, 1500.002]),
        powers=np.array([-40.268, -40.280, -40.275]),
        monitor_powers=np.array([7.58, 7.59, 7.60]),
        scan_params={
            "start_wl": 1500.0,
            "stop_wl": 1630.0,
            "step": 0.001,
            "speed": 20.0,
            "power": 0.0,
        },
        timestamp="2026-04-13T10:30:00",
        mpm_range=1,
    )
    il = meas.powers - ref.powers
    return ILMeasurement(
        reference=ref,
        measurement=meas,
        il=il,
        wavelengths=ref.wavelengths,
    )


def _read_csv_rows(filepath: str) -> list[list[str]]:
    with open(filepath, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


# ---------------------------------------------------------------------------
# Raw CSV tests
# ---------------------------------------------------------------------------


class TestSaveRawCsv:
    def test_creates_file(self):
        """save_raw_csv should create a file at the given path."""
        scan = _make_scan_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "raw.csv")
            save_raw_csv(scan, TSL_IDN, MPM_IDN, path)
            assert os.path.isfile(path)

    def test_header_contains_metadata(self):
        """The header should include Software, TSL, MPM, and Start lines."""
        scan = _make_scan_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "raw.csv")
            save_raw_csv(scan, TSL_IDN, MPM_IDN, path)
            rows = _read_csv_rows(path)

            # Collect all non-empty cell text for easy searching
            all_text = " ".join(cell for row in rows for cell in row)

            assert "santecpro" in all_text
            assert "TSL-550" in all_text
            assert "MPM-210" in all_text
            assert "Start" in all_text
            assert "1500.000000" in all_text

    def test_data_rows_present(self):
        """After the data header row, the first data row should match scan values."""
        scan = _make_scan_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "raw.csv")
            save_raw_csv(scan, TSL_IDN, MPM_IDN, path)
            rows = _read_csv_rows(path)

            # Find the data header row
            data_start = None
            for i, row in enumerate(rows):
                if row and row[0] == "Wavelength(nm)":
                    data_start = i + 1
                    break

            assert data_start is not None, "Data header not found"
            assert data_start < len(rows), "No data rows after header"

            first_row = rows[data_start]
            assert float(first_row[0]) == pytest.approx(1500.0)
            assert float(first_row[1]) == pytest.approx(7.58)
            assert float(first_row[2]) == pytest.approx(-33.268)


# ---------------------------------------------------------------------------
# Loss CSV tests
# ---------------------------------------------------------------------------


class TestSaveLossCsv:
    def test_creates_file(self):
        """save_loss_csv should create a file at the given path."""
        il_meas = _make_il_measurement()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "loss.csv")
            save_loss_csv(il_meas, TSL_IDN, MPM_IDN, path)
            assert os.path.isfile(path)

    def test_data_contains_il(self):
        """Data rows should contain IL values computed as meas - ref."""
        il_meas = _make_il_measurement()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "loss.csv")
            save_loss_csv(il_meas, TSL_IDN, MPM_IDN, path)
            rows = _read_csv_rows(path)

            # Find the data header row
            data_start = None
            for i, row in enumerate(rows):
                if row and row[0] == "Wavelength(nm)":
                    data_start = i + 1
                    break

            assert data_start is not None, "Data header not found"

            # Expected IL = meas - ref = (-40.268) - (-33.268) = -7.0
            first_row = rows[data_start]
            assert float(first_row[0]) == pytest.approx(1500.0)
            assert float(first_row[1]) == pytest.approx(-7.0)

            # Second row
            second_row = rows[data_start + 1]
            assert float(second_row[1]) == pytest.approx(-7.0)


def test_official_sample_column_layout_and_precision(tmp_path):
    from santecpro.session import ScanSession
    from santecpro.exporter import save_record_csv
    session = ScanSession()
    reference = _make_scan_result()
    reference.scan_params['mpm_averaging_time_ms'] = .05
    session.add(reference, is_reference=True)
    measurement = _make_scan_result()
    measurement.powers -= 7
    measurement.scan_params['mpm_averaging_time_ms'] = .05
    record = session.add(measurement)
    raw, loss = tmp_path / 'raw.csv', tmp_path / 'loss.csv'
    save_record_csv(record, raw, 'raw')
    save_record_csv(record, loss, 'loss')
    raw_rows, loss_rows = _read_csv_rows(raw), _read_csv_rows(loss)
    assert raw_rows[14] == ['Wavelength(nm)', 'Monitor-R1(dBm)', 'Raw_M1-Ch1-R1(dBm)', '', '']
    assert loss_rows[14] == ['Wavelength(nm)', 'IL_M1_CH1', '', '', '']
    assert raw_rows[15] == ['1500.00000', '7.58000', '-40.26800', '', '']
    assert loss_rows[15] == ['1500.00000000', '-7.00000000', '', '', '']
    assert raw_rows[11] == ['Averaging Time', '0.000050', 's', '', '']
    assert raw_rows[13][0] == 'TSL PM- range'
    assert raw_rows[5][0] == 'PowerMonitor'
    assert raw_rows[0][0] == '2026/4/13'
    assert b'\r\n' in raw.read_bytes()


def test_multi_channel_export_does_not_mislabel_channel_or_module(tmp_path):
    scan = _make_scan_result()
    scan.scan_params['mpm_module'] = 1  # zero-based DLL slot
    scan.channel_powers = {2: scan.powers, 4: scan.powers - 3}
    path = tmp_path / 'raw.csv'
    save_raw_csv(scan, TSL_IDN, MPM_IDN, path)
    rows = _read_csv_rows(path)
    assert rows[14] == ['Wavelength(nm)', 'Monitor-R1(dBm)', 'Raw_M2-Ch2-R1(dBm)', 'Raw_M2-Ch4-R1(dBm)', '', '']
    assert len(rows) == 18


def test_mismatched_raw_lengths_rejected_before_overwriting(tmp_path):
    path = tmp_path / 'raw.csv'
    path.write_text('existing')
    scan = _make_scan_result()
    scan.monitor_powers = np.array([7])
    with pytest.raises(ValueError, match='mismatched'):
        save_raw_csv(scan, TSL_IDN, MPM_IDN, path)
    assert path.read_text() == 'existing'


@pytest.mark.parametrize('mpm_range', [1, 2, 3, 4, 5])
def test_raw_loss_and_reference_export_captured_hardware_range(tmp_path, mpm_range):
    from santecpro.session import ScanSession
    from santecpro.exporter import save_record_csv
    session = ScanSession()
    reference = _make_scan_result()
    reference.mpm_range = 2
    ref_record = session.add(reference, is_reference=True)
    measurement = _make_scan_result()
    measurement.mpm_range = mpm_range
    record = session.add(measurement)
    # Later input/UI changes must not alter the history record's exported setting.
    measurement.mpm_range = 5
    for kind in ('raw', 'loss'):
        path = tmp_path / f'{kind}.csv'
        save_record_csv(record, path, kind)
        rows = _read_csv_rows(path)
        assert rows[12] == ['Power meter range', '', 'dBm', 'MPM range', str(mpm_range)]
        assert rows[14][0] == 'Wavelength(nm)'
    path = tmp_path / 'reference.csv'
    save_record_csv(ref_record, path, 'raw')
    assert _read_csv_rows(path)[12][-2:] == ['MPM range', '2']


def test_range_index_does_not_replace_explicit_dbm_range(tmp_path):
    scan = _make_scan_result()
    scan.mpm_range = 3
    scan.scan_params['power_meter_range_dbm'] = -10
    path = tmp_path / 'raw.csv'
    save_raw_csv(scan, TSL_IDN, MPM_IDN, path)
    assert _read_csv_rows(path)[12] == ['Power meter range', '-10', 'dBm', 'MPM range', '3']


def test_instrument_response_terminators_do_not_add_physical_header_lines(tmp_path):
    scan = _make_scan_result()
    path = tmp_path / 'raw.csv'
    save_raw_csv(scan, TSL_IDN + '\r\n', MPM_IDN + '\n', path)
    lines = path.read_text().splitlines()
    assert lines[14].startswith('Wavelength(nm),')
    loaded = np.loadtxt(path, delimiter=',', skiprows=15, usecols=(0, 1, 2))
    np.testing.assert_allclose(loaded[:, 0], scan.wavelengths)
    rows = _read_csv_rows(path)
    assert rows[2][4] == TSL_IDN.split(',')[3].strip()
    assert rows[3][4] == MPM_IDN.split(',')[3].strip()


def test_loss_csv_records_new_sign_convention(tmp_path):
    from santecpro.session import ScanSession
    from santecpro.exporter import save_record_csv
    session=ScanSession()
    ref=_make_scan_result()
    session.add(ref,is_reference=True)
    meas=_make_scan_result()
    meas.powers -= 10
    record=session.add(meas)
    path=tmp_path/'loss.csv'
    save_record_csv(record,path,'loss')
    rows=_read_csv_rows(path)
    assert rows[1][-2:] == ['Loss convention','measurement - reference']
    assert float(rows[15][1]) == -10
