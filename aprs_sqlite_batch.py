"""Bounded RAM queues and batched SQLite commits for SD-card-hosted APRS logs.

Each database gets one background writer. Enqueue never touches SQLite; at most
100 rows (default) are committed per transaction, or after 10s of inactivity
since the first buffered row. Interactive reads may explicitly flush.

A power failure can lose the buffered interval and, with WAL/NORMAL, some
recently committed data. WAL preserves database consistency; it is not a UPS.
"""
from __future__ import annotations

from collections import deque
import logging
import threading
import time
from typing import Callable

LOG = logging.getLogger('ok5tvr.aprs')


class SQLiteBatcher:
    """Single-writer asynchronous batch queue with deterministic drain on close."""

    def __init__(self, write_batch: Callable, *, name: str,
                 batch_size: int = 100, flush_seconds: float = 10.0,
                 max_pending: int = 1000):
        if not 1 <= batch_size <= max_pending or flush_seconds <= 0:
            raise ValueError('Invalid SQLite batch settings')
        self.write_batch = write_batch
        self.name = name
        self.batch_size = batch_size
        self.flush_seconds = float(flush_seconds)
        self.max_pending = max_pending

        self.cv = threading.Condition()
        self.queue = deque()
        self.inflight = 0
        self.first_pending_at = None
        self.force_flush = False
        self.closing = False
        self.closed = False
        self.accepted = 0
        self.written = 0
        self.batches = 0
        self.dropped = 0
        self.write_errors = 0
        self.last_error = ''
        self.last_flush_utc = None
        self.worker = threading.Thread(target=self._run, name=name, daemon=True)
        self.worker.start()

    def add(self, record) -> bool:
        with self.cv:
            if self.closing or self.closed:
                raise RuntimeError(f'{self.name}: writer is closing')
            if len(self.queue) + self.inflight >= self.max_pending:
                self.dropped += 1
                return False
            if not self.queue:
                self.first_pending_at = time.monotonic()
            self.queue.append(record)
            self.accepted += 1
            if len(self.queue) >= self.batch_size:
                self.cv.notify_all()
            return True

    def _run(self):
        while True:
            with self.cv:
                while True:
                    if not self.queue:
                        if self.closing:
                            return
                        self.force_flush = False
                        self.cv.wait()
                        continue
                    if (self.closing or self.force_flush
                            or len(self.queue) >= self.batch_size):
                        break
                    remaining = self.flush_seconds - (time.monotonic() - self.first_pending_at)
                    if remaining <= 0:
                        break
                    self.cv.wait(remaining)
                size = min(self.batch_size, len(self.queue))
                batch = [self.queue.popleft() for _ in range(size)]
                self.inflight = size
                self.first_pending_at = time.monotonic() if self.queue else None
            error = None
            try:
                self.write_batch(batch)
            except Exception as exc:
                error = exc
                LOG.warning('%s: SQLite batch write failed: %s', self.name, exc)
            with self.cv:
                self.inflight = 0
                if error is not None:
                    self.queue.extendleft(reversed(batch))
                    self.first_pending_at = time.monotonic()
                    self.write_errors += 1
                    self.last_error = str(error)[:180]
                else:
                    self.written += size
                    self.batches += 1
                    self.last_error = ''
                    self.last_flush_utc = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                if not self.queue:
                    self.force_flush = False
                self.cv.notify_all()
                if error is not None:
                    # Do not busy-loop when the SD card is missing/full.
                    self.cv.wait(timeout=1.0)

    def flush(self, timeout: float = 10.0) -> None:
        """Wait until all records accepted *before this call* are committed."""
        end = time.monotonic() + timeout
        with self.cv:
            target = self.accepted
            self.force_flush = True
            self.cv.notify_all()
            while self.written < target:
                remaining = end - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f'{self.name}: flush timeout; {self.last_error}')
                self.cv.wait(remaining)

    def stats(self) -> dict:
        with self.cv:
            return {
                'pending': len(self.queue) + self.inflight,
                'batches_written': self.batches,
                'records_written': self.written,
                'dropped': self.dropped,
                'write_errors': self.write_errors,
                'last_error': self.last_error,
                'last_flush_utc': self.last_flush_utc,
                'batch_size': self.batch_size,
                'flush_seconds': self.flush_seconds,
                'max_pending': self.max_pending,
            }

    def close(self, timeout: float = 15.0) -> None:
        with self.cv:
            if self.closed:
                return
            self.closing = True
            self.force_flush = True
            self.cv.notify_all()
        self.worker.join(timeout=timeout)
        if self.worker.is_alive():
            raise TimeoutError(f'{self.name}: shutdown flush timed out; {self.stats()}')
        with self.cv:
            self.closed = True
            if self.queue or self.inflight:
                raise RuntimeError(f'{self.name}: uncommitted rows on close')
