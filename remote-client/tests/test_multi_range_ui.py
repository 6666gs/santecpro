import csv
import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication
from santecpro.ui_app import ScanMainWindow
from santecpro.jobscript import parse_job, JobScriptError
from santecpro.remote import RemoteScanner
from santecpro.results import ScanResult
from santecpro.exporter import save_raw_csv
from santecpro.raw_import import load_raw_reference


def test_script_range_defaults_overrides_and_reverse():
    job=parse_job('set range=5,2,3\nscan a 1550 1551 step=10pm speed=1 dir=both\nscan b 1550 1551 step=10pm speed=1 range=4')
    assert [s.mpm_ranges for s in job.segments]==[(2,3,5),(2,3,5),()]
    assert job.segments[-1].mpm_range==4
    with pytest.raises(JobScriptError): parse_job('set range=2,2')


def test_ui_selection_and_single_range_default():
    app=QApplication.instance() or QApplication([])
    w=ScanMainWindow(auto_connect=False)
    try:
        assert w._scan_settings().mpm_ranges==()
        w.multi_range_check.setChecked(True)
        assert w._scan_settings().mpm_ranges==(2,3,4,5)
        assert not w.range_combo.isEnabled()
        for check in w.range_checks: check.setChecked(False)
        with pytest.raises(ValueError): w._scan_settings()
    finally: w.close()


def test_reject_old_server_that_only_echoes_requested_ranges(monkeypatch):
    scanner=RemoteScanner('http://unused')
    monkeypatch.setattr(scanner,'_post',lambda *args: {'scan_params':{'mpm_ranges':[2,4]}})
    with pytest.raises(RuntimeError,match='Windows'):
        scanner.run_stsprocess_scan(1550,1551,.01,1,mpm_ranges=(2,4),plot=False)


def test_merged_raw_metadata_survives_reference_import(tmp_path):
    p=tmp_path/'merged.csv'
    scan=ScanResult(np.array([1550.,1551.]),np.array([-5.,-60.]),np.array([7.,7.]),
        {'mpm_ranges':[2,4,5],'range_merge_method':'MPM-211 STSProcess 2.2.7 threshold selection'},mpm_range=0)
    save_raw_csv(scan,'','',p)
    rows=list(csv.reader(p.open()))
    assert rows[12][3:5]==['MPM ranges','2+4+5']
    reloaded=load_raw_reference(p)
    assert reloaded.mpm_range==0
    assert reloaded.scan_params['mpm_ranges']==[2,4,5]
    np.testing.assert_array_equal(reloaded.powers,scan.powers)
