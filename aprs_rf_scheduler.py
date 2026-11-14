"""Bounded priority-based RF output scheduler, shared by serial and TCP KISS.

This queues *only* packets explicitly requested by other APRS subsystems.
It cannot enable any RF mode. The transport rechecks DIGI and IS->RF
permissions immediately before a physical write.
"""
from __future__ import annotations

from collections import Counter, deque
import heapq
import queue
import threading
import time


def category_priority(category: str) -> int:
    if category.startswith('msgack:'):
        return 0
    if category.startswith('msg:'):
        return 1
    if category in ('manual', 'network_manual', 'status', 'position', 'object'):
        return 2
    if category == 'digi':
        return 3
    if category == 'igate_is_to_rf':
        return 4
    return 5


class RFOutputScheduler:
    """queue-compatible drop-in for a KISS TX queue, never starts a thread.

    A serial/TCP KISS reader polls get_nowait(). Short packets take precedence
    over low-priority telemetry without preempting an already active RF write.
    """

    def __init__(self, max_pending=12, min_gap_s=0.0, max_per_minute=30,
                 clock=time.monotonic):
        self.lock = threading.RLock()
        self.clock = clock
        self.heap = []
        self.seq = 0
        self.times = deque()
        self.last_dequeued = float('-inf')
        self.enqueued = Counter()
        self.dequeued = Counter()
        self.dropped = 0
        self.expired = 0
        self.configure(max_pending=max_pending, min_gap_s=min_gap_s,
                       max_per_minute=max_per_minute)

    def configure(self, *, max_pending=None, min_gap_s=None, max_per_minute=None):
        with self.lock:
            if max_pending is not None:
                if type(max_pending) is not int or not 1 <= max_pending <= 32:
                    raise ValueError('RF Scheduler max_pending: 1-32')
                self.max_pending = max_pending
            if min_gap_s is not None:
                if type(min_gap_s) not in (int, float) or not 0 <= min_gap_s <= 15:
                    raise ValueError('RF Scheduler min_gap_s: 0-15')
                self.min_gap_s = float(min_gap_s)
            if max_per_minute is not None:
                if type(max_per_minute) is not int or not 1 <= max_per_minute <= 60:
                    raise ValueError('RF Scheduler rate: 1-60 per minute')
                self.max_per_minute = max_per_minute

    def put_nowait(self, entry):
        payload, category = entry
        if not isinstance(payload, bytes) or len(payload) > 1000 or not payload:
            raise ValueError('Invalid KISS TX bytes')
        if not isinstance(category, str) or len(category) > 64:
            raise ValueError('Invalid TX category')
        with self.lock:
            if len(self.heap) >= self.max_pending:
                self.dropped += 1
                raise queue.Full()
            self.seq += 1
            heapq.heappush(self.heap, (category_priority(category), self.seq,
                                       self.clock(), bytes(payload), category))
            self.enqueued[category.split(':')[0]] += 1

    def get_nowait(self):
        with self.lock:
            now = self.clock()
            # Drop expired packets after a long-lived TNC or channel outage.
            while self.heap:
                priority, seq, queued_at, payload, category = self.heap[0]
                if now - queued_at <= 90:
                    break
                heapq.heappop(self.heap)
                self.expired += 1
            if not self.heap:
                raise queue.Empty()
            if now - self.last_dequeued < self.min_gap_s:
                raise queue.Empty()
            while self.times and now - self.times[0] >= 60:
                self.times.popleft()
            if len(self.times) >= self.max_per_minute:
                raise queue.Empty()
            priority, seq, queued_at, payload, category = heapq.heappop(self.heap)
            self.last_dequeued = now
            self.times.append(now)
            self.dequeued[category.split(':')[0]] += 1
            return payload, category

    def qsize(self):
        with self.lock:
            return len(self.heap)

    def empty(self):
        return self.qsize() == 0

    def snapshot(self):
        with self.lock:
            now = self.clock()
            return {'pending':len(self.heap), 'max_pending':self.max_pending,
                    'min_gap_s':self.min_gap_s,
                    'max_per_minute':self.max_per_minute,
                    'in_last_minute':sum(now-t < 60 for t in self.times),
                    'by_category':dict(Counter(category.split(':')[0]
                                        for *_, category in self.heap)),
                    'sent_by_category':dict(self.dequeued),
                    'rejected_full':self.dropped, 'expired':self.expired,
                    'next_tx_wait_s':round(max(0.0,
                       self.min_gap_s - (now-self.last_dequeued)),1)}
