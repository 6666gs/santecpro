from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
import server
from multi_range import RangeMerger, parse_ranges


def data(rng, p, q=None):
    return dict(mpm_range=rng, wavelengths=[1550.,1551.,1552.], powers=p,
                monitor_powers=[7.+rng]*3, channel_powers={'1':p,'2':q or p},
                scan_params={'mpm_channel':1}, timestamp=str(rng))


def test_official_threshold_boundary_multichannel_and_first_monitor():
    merger=RangeMerger()
    first=data(2,[-10.,-10.01,-50.],[-5.,-40.,-5.])
    original=deepcopy(first)
    merger.add(first)
    merged=merger.add(data(3,[99.,-11.,-45.],[99.,-35.,99.]))
    assert merged['powers']==[-10.,-11.,-45.]
    assert merged['channel_powers']['2']==[-5.,-35.,-5.]
    assert merged['monitor_powers']==[9.]*3
    assert first==original
    merged=merger.add(data(5,[99.,99.,-65.],[99.,-55.,99.]))
    assert merged['powers']==[-10.,-11.,-65.]
    assert merged['scan_params']['range_merge_source_counts']['1']=={'2':1,'3':1,'5':1}


@pytest.mark.parametrize('ranges',[[0,2],[2,6],[2,2],[True,2],['2',3],'2,3'])
def test_reject_bad_ranges(ranges):
    with pytest.raises(ValueError): parse_ranges({'mpm_ranges':ranges})


def test_reverse_grid_and_mismatch_rejection():
    merger=RangeMerger()
    a=data(2,[-5.,-20.,-45.]);a['wavelengths'].reverse();merger.add(a)
    b=data(4,[-5.,-20.,-60.]);b['wavelengths'].reverse()
    assert merger.add(b)['powers']==[-5.,-20.,-60.]
    c=data(5,[-5.,-20.,-70.])
    with pytest.raises(ValueError,match='identical'): merger.add(c)


@pytest.mark.parametrize('cancel,fail',[(False,False),(True,False),(False,True)])
def test_endpoint_runs_one_locked_batch_and_never_returns_partial(monkeypatch,cancel,fail):
    calls=[]
    server.scan_cancel.clear();server._set_scan_state(running=False,phase='idle')
    def scan(settings,cancel_event):
        calls.append(settings.mpm_range)
        if settings.mpm_range==2 and cancel: cancel_event.set()
        if settings.mpm_range==4 and fail: raise RuntimeError('read failed')
        p=[-5.,-25.,-45.] if settings.mpm_range==2 else [-5.,-30.,-60.]
        return SimpleNamespace(wavelengths=[1550.,1551.,1552.],powers=p,monitor_powers=[7.]*3,
              channel_powers={1:p},actual_step=.01,requested_points=3,target_points=3,
              raw_points=3,mpm_expected_raw_points=3,mpm_completed_points=3,csv_path='',
              tsl_idn='TSL',mpm_idn='MPM',averaging_time_ms=.05)
    monkeypatch.setattr(server,'run_stsprocess_scan',scan)
    with server.app.test_client() as client:
        response=client.post('/api/scan/stsprocess',json=dict(start_wl=1550,stop_wl=1552,step=.01,speed=1,mpm_ranges=[4,2]))
    if cancel or fail:
        assert response.status_code==(409 if cancel else 500)
        assert 'powers' not in response.json
    else:
        assert response.status_code==200
        assert response.json['powers']==[-5.,-30.,-60.]
        assert response.json['mpm_range']==0
        assert response.json['scan_params']['mpm_ranges']==[2,4]
    assert calls==([2] if cancel else [2,4])
    assert not server.scan_state['running']
    server.scan_cancel.clear()
