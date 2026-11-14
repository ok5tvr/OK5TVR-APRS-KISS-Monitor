"""SD-card-friendly SQLite batch writer and journal/archive regression tests."""
from __future__ import annotations

import sqlite3
import tempfile
import threading
import time
from pathlib import Path
import unittest

from aprs_archive import APRSArchive
from aprs_features import encode_ui_packet
from aprs_operations import Journal
from aprs_protocol import decode_ax25
from aprs_sqlite_batch import SQLiteBatcher
from aprs_weather import decode_weather


def wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def packet(payload='!4944.40N/01322.20E>test'):
    return decode_ax25(encode_ui_packet('OK1ABC-7', 'APRS', '', payload))


class BatchWriterTests(unittest.TestCase):
    def test_flush_at_100_and_flush_after_timeout(self):
        results = []
        cv = threading.Lock()

        def write_batch(records):
            with cv:
                results.append(tuple(records))

        b = SQLiteBatcher(write_batch, name='test-batch', batch_size=3,
                          flush_seconds=.12, max_pending=12)
        try:
            self.assertTrue(b.add('a'))
            self.assertTrue(b.add('b'))
            self.assertEqual(results, [])  # Two packets are RAM-only, not committed.
            self.assertTrue(b.add('c'))
            self.assertTrue(wait_for(lambda: b.stats()['records_written'] == 3))
            self.assertEqual(results[0], ('a', 'b', 'c'))
            self.assertTrue(b.add('d'))
            self.assertTrue(wait_for(lambda: b.stats()['records_written'] == 4))
            self.assertEqual(results[-1], ('d',))
            self.assertEqual(b.stats()['batches_written'], 2)
            self.assertEqual(b.stats()['pending'], 0)
        finally:
            b.close()

    def test_shutdown_drains_pending_without_10_second_delay(self):
        committed = []
        b = SQLiteBatcher(lambda rows: committed.extend(rows),
                          name='shutdown-test', batch_size=100, flush_seconds=10)
        self.assertTrue(b.add('last-packet'))
        self.assertEqual(committed, [])
        b.close()
        self.assertEqual(committed, ['last-packet'])
        self.assertEqual(b.stats()['pending'], 0)
        b.close()  # idempotent

    def test_bounded_queue_rejects_excess_instead_of_growing_indefinitely(self):
        working = threading.Event()
        release = threading.Event()
        committed = []

        def write(records):
            working.set()
            release.wait(2)
            committed.extend(records)

        b = SQLiteBatcher(write, name='queue-limit-test', batch_size=2,
                          flush_seconds=10, max_pending=3)
        try:
            self.assertTrue(b.add(1))
            self.assertTrue(b.add(2))
            self.assertTrue(working.wait(2))
            self.assertTrue(b.add(3))
            self.assertFalse(b.add(4))
            self.assertEqual(b.stats()['dropped'], 1)
            self.assertEqual(b.stats()['pending'], 3)
        finally:
            release.set()
            b.close()
        self.assertEqual(committed, [1, 2, 3])

    def test_failed_transaction_is_retried_not_silently_discarded(self):
        attempts = []
        written = []

        def intermittent(records):
            attempts.append(True)
            if len(attempts) == 1:
                raise OSError('simulated card not ready')
            written.extend(records)

        b = SQLiteBatcher(intermittent, name='retry-test', batch_size=2,
                          flush_seconds=.05, max_pending=10)
        try:
            b.add('one')
            b.add('two')
            b.flush(timeout=4)
            self.assertEqual(written, ['one', 'two'])
            self.assertEqual(b.stats()['write_errors'], 1)
            self.assertEqual(b.stats()['pending'], 0)
        finally:
            b.close()


class SQLStorageTests(unittest.TestCase):
    def test_archive_wal_normal_and_lazy_flush_without_rapid_commits(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'history.sqlite3'
            archive = APRSArchive(path, retention_days=30, max_rows=1000)
            try:
                self.assertEqual(archive.db.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
                self.assertEqual(archive.db.execute('PRAGMA synchronous').fetchone()[0], 1)
                wx = decode_weather(b'_11092215c120s010g015t050h65b10132')
                archive.add(packet(), wx)
                self.assertEqual(archive.summary()['packets'], 1)
                self.assertEqual(archive.summary()['weather'], 1)
                self.assertEqual(archive.summary()['positions'], 1)
                self.assertEqual(archive.summary()['storage']['pending'], 1)
                with sqlite3.connect(path) as db:
                    # The packet is still only buffered, not written to the SD.
                    self.assertEqual(db.execute('SELECT count(*) FROM packets').fetchone()[0], 0)
                # Explicit history view forces a batch so users see fresh data.
                self.assertEqual(len(archive.packets()), 1)
                self.assertEqual(len(archive.positions('OK1ABC-7')), 1)
                self.assertEqual(len(archive.weather_rows()), 1)
                self.assertEqual(archive.summary()['storage']['pending'], 0)
                self.assertEqual(archive.summary()['storage']['batches_written'], 1)
                archive.add(packet('>additional record'))
            finally:
                archive.close()
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM packets').fetchone()[0], 2)

    def test_journal_read_flush_and_shutdown_persist(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'operations.sqlite3'
            journal = Journal(path)
            self.assertEqual(journal.con.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
            self.assertEqual(journal.con.execute('PRAGMA synchronous').fetchone()[0], 1)
            try:
                journal.log('RX', 'accepted', 'OK1ABC-7')
                with sqlite3.connect(path) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0], 0)
                self.assertEqual(journal.read(limit=10)[0]['source'], 'OK1ABC-7')
                journal.log('TX', 'written', 'OK5TVR-10')
                self.assertEqual(journal.stats()['pending'], 1)
            finally:
                journal.close()
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0], 2)


if __name__ == '__main__':
    unittest.main()
