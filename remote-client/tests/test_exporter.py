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
    il = ref.powers - meas.powers
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
        """Data rows should contain IL values computed as ref - meas."""
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

            # Expected IL = ref - meas = (-33.268) - (-40.268) = 7.0
            first_row = rows[data_start]
            assert float(first_row[0]) == pytest.approx(1500.0)
            assert float(first_row[1]) == pytest.approx(7.0)

            # Second row
            second_row = rows[data_start + 1]
            assert float(second_row[1]) == pytest.approx(7.0)


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
    assert loss_rows[15] == ['1500.00000000', '7.00000000', '', '', '']
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
