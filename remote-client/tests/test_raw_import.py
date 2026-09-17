import csv
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox
from santecpro.raw_import import load_raw_reference
from santecpro.session import ScanSession
from santecpro.exporter import save_record_csv
from santecpro.ui_app import ScanMainWindow
from test_ui_script import pump


def write_raw(path, *, rows=None, headers=None):
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['2026/9/16', '18:25:07'])
        w.writerow(['TSL','SANTEC','TSL-550','123','v1\r\n'])
        w.writerow(['PowerMeter','SANTEC','MPM-210','234','v2\n'])
        w.writerow(['Averaging Time','.00005','s'])
        w.writerow(['Power meter range','0.0','dBm','',''])
        w.writerow(headers or ['Wavelength(nm)','Monitor-R1(dBm)','Raw_M1-Ch1-R1(dBm)','Raw_M1-Ch2-R1(dBm)','',''])
        w.writerows(rows or [[1550,7,-2,-4,'',''],[1551,7,-3,-5,'','']])


def test_official_import_reference_loss_and_raw_roundtrip(tmp_path):
    p=tmp_path/'official.csv';write_raw(p)
    scan=load_raw_reference(p)
    assert scan.channels() == [1,2] and scan.mpm_range == 0
    assert scan.scan_params['mpm_averaging_time_ms'] == .05
    assert scan.scan_params['tsl_idn'].endswith('v1')
    session=ScanSession();ref=session.add(scan,is_reference=True)
    scan.channel_powers[1] -= 10
    scan.channel_powers[2] -= 5
    record=session.add(scan)
    np.testing.assert_allclose(record.loss[1],-10)
    np.testing.assert_allclose(record.loss[2],-5)
    output=tmp_path/'ref_raw.csv';save_record_csv(ref,output,'raw')
    reloaded=load_raw_reference(output)
    assert reloaded.mpm_range == 0  # unknown must not become a made-up Range 1
    np.testing.assert_array_equal(reloaded.powers,ref.raw.powers)


@pytest.mark.parametrize('rows,headers', [
    ([[1550,7,-2,-4],[1550,7,-2,-4]],None),
    ([[1550,7,-2,-4],[1551,float('nan'),-2,-4]],None),
    ([[1550,7,-2,-4],[1551,7]],None),
    (None,['Wavelength(nm)','IL_M1_CH1','','']),
    (None,['Wavelength(nm)','Monitor-R1(dBm)','Raw_M1-Ch1-R2(dBm)']),
])
def test_reject_corrupt_loss_and_ambiguous_range_files(tmp_path,rows,headers):
    p=tmp_path/'bad.csv';write_raw(p,rows=rows,headers=headers)
    with pytest.raises(ValueError):load_raw_reference(p)


def test_reverse_wavelength_import_and_interpolated_loss(tmp_path):
    p=tmp_path/'reverse.csv';write_raw(p,rows=[[1551,7,-3,-5],[1550,7,-2,-4]])
    reference=load_raw_reference(p)
    from santecpro.results import ScanResult
    from santecpro.reference import calculate_reference_il
    measurement=ScanResult(np.array([1550.5]),np.array([-12.5]),np.array([0.]))
    np.testing.assert_allclose(calculate_reference_il(reference,measurement).il,[-10])


def test_gui_import_offline_and_failed_import_preserves_reference(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    p=tmp_path/'raw.csv';write_raw(p)
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *a: (str(p),''))
    monkeypatch.setattr(QMessageBox,'critical',lambda *a: None)
    w=ScanMainWindow(auto_connect=False)
    try:
        w._import_reference()
        pump(app,lambda:w._thread is None)
        ref=w._session.reference
        assert ref is not None and w._last_record.is_reference
        assert w._last_record.saved and w.history_combo.count() == 1
        assert p.name in w.history_combo.currentText()
        p.write_text('not raw')
        w._import_reference()
        pump(app,lambda:w._thread is None)
        assert w._session.reference is ref and w.history_combo.count() == 1
    finally:
        w.close()
