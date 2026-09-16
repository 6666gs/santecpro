import threading
from unittest.mock import Mock
from alignment_cache import AlignmentMeterCache


def cache():
    now = [0.0]
    obj = AlignmentMeterCache(threading.RLock(), clock=lambda: now[0])
    obj._schedule = Mock()  # deterministic expiration, no real timer
    return obj, now


def test_reuse_and_idle_disconnect():
    c, now = cache()
    meter = Mock()
    factory = Mock(return_value=meter)
    for t in range(20):
        now[0] = t / 10
        assert c.get('GPIB0::1', factory) is meter
        c.touch()
    factory.assert_called_once()
    meter.connect.assert_called_once()
    now[0] = 6.0
    c.expire()
    meter.disconnect.assert_not_called()
    now[0] = 7.0
    c.expire()
    meter.disconnect.assert_called_once()
    assert c.meter is None


def test_address_change_and_stale_expiration():
    c, now = cache()
    a, b = Mock(), Mock()
    c.get('A', lambda _: a)
    old_generation = c._generation
    c.get('B', lambda _: b)
    a.disconnect.assert_called_once()
    now[0] = 100
    c.expire(old_generation)
    b.disconnect.assert_not_called()
    c.close()
    b.disconnect.assert_called_once()
