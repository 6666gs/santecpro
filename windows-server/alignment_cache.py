"""Short-lived MPM connection reuse for sequential alignment reads."""
import logging
import threading
import time


class AlignmentMeterCache:
    def __init__(self, lock, *, idle_seconds=5.0, clock=time.monotonic):
        self.lock = lock
        self.idle_seconds = idle_seconds
        self.clock = clock
        self.meter = None
        self.address = None
        self.last_used = 0.0
        self._timer = None
        self._generation = 0

    def get(self, address, factory):
        # Caller holds the server instrument lock for the full hardware request.
        if self.meter is not None and self.address != address:
            self.close()
        if self.meter is None:
            meter = factory(address)
            try:
                meter.connect()
            except Exception:
                meter.disconnect()
                raise
            self.meter, self.address = meter, address
            self._schedule()
        self.last_used = self.clock()
        return self.meter

    def touch(self):
        self.last_used = self.clock()

    def _schedule(self):
        self._generation += 1
        self._timer = threading.Timer(1.0, self.expire, args=(self._generation,))
        self._timer.daemon = True
        self._timer.start()

    def expire(self, generation=None):
        with self.lock:
            if generation is not None and generation != self._generation:
                return
            if self._timer is not None:
                self._timer.cancel()
            self._timer = None
            if self.meter is None:
                return
            if self.clock() - self.last_used >= self.idle_seconds:
                self.close()
            else:
                self._schedule()

    def close(self):
        # No LD or shutter changes; release only the communication handle.
        self._generation += 1
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        meter, self.meter = self.meter, None
        self.address = None
        if meter is not None:
            try:
                meter.disconnect()
            except Exception:
                logging.getLogger(__name__).exception('Alignment MPM disconnect failed')
