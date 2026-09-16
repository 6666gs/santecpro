import numpy as np
import pytest

from santecpro.results import ScanResult
from santecpro.session import ScanSession
from santecpro.exporter import save_record_csv


def scan(power=-10, *, channels=(1, 2), wavelengths=(1550, 1551)):
    wl = np.array(wavelengths, dtype=float)
    return ScanResult(wavelengths=wl, powers=np.full(len(wl), power, dtype=float),
                      monitor_powers=np.full(len(wl), 7.0),
                      channel_powers={ch: np.full(len(wl), power - ch, dtype=float) for ch in channels},
                      scan_params={'start_wl':wl[0], 'stop_wl':wl[-1], 'step':.01,
                                   'mpm_module':0, 'mpm_averaging_time_ms':.05},
                      timestamp='2026-09-16T12:30:00+00:00')


def test_reference_is_raw_only_and_measurements_hold_both(tmp_path):
    session = ScanSession()
    ref = session.add(scan(-1), is_reference=True)
    measured = session.add(scan(-11))
    assert ref.is_reference and not ref.loss
    assert measured.reference_index == 0
    for ch in (1, 2):
        np.testing.assert_allclose(measured.loss[ch], [10, 10])
    raw_before = measured.raw.channel_powers[1].copy()
    save_record_csv(measured, tmp_path / 'raw.csv', 'raw')
    save_record_csv(measured, tmp_path / 'loss.csv', 'loss')
    np.testing.assert_array_equal(measured.raw.channel_powers[1], raw_before)
    np.testing.assert_allclose(measured.loss[1], [10, 10])
    with pytest.raises(ValueError, match='raw'):
        save_record_csv(ref, tmp_path / 'invalid_loss.csv', 'loss')
    assert not (tmp_path / 'invalid_loss.csv').exists()


def test_reference_changes_only_affect_future_scans():
    session = ScanSession()
    original = scan(-1)
    session.add(original, is_reference=True)
    original.channel_powers[1][:] = 100  # input mutation cannot change the stored reference
    first = session.add(scan(-11))
    session.add(scan(-3), is_reference=True)
    second = session.add(scan(-11))
    session.clear_reference()
    third = session.add(scan(-11))
    np.testing.assert_allclose(first.loss[1], 10)
    np.testing.assert_allclose(second.loss[1], 8)
    assert not third.loss
    assert first.reference_index == 0 and second.reference_index == 2
    assert len(session.records) == 5


@pytest.mark.parametrize('measurement', [scan(wavelengths=(1549,1551)), scan(channels=(1,3))])
def test_incompatible_reference_preserves_raw_with_explicit_loss_error(measurement):
    session = ScanSession()
    session.add(scan(), is_reference=True)
    record = session.add(measurement)
    assert not record.loss
    assert record.loss_error
    np.testing.assert_array_equal(record.raw.wavelengths, measurement.wavelengths)


def test_set_reference_from_measured_history_does_not_rewrite_old_losses():
    session = ScanSession()
    first = session.add(scan(-1))
    assert not first.loss
    session.set_reference(0)
    measured = session.add(scan(-11))
    session.clear_reference()
    np.testing.assert_allclose(measured.loss[1], 10)
    assert session.records[0].is_reference
