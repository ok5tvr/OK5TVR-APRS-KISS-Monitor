"""Bounded, persistent, searchable APRS packet, GPS and weather archive.

Database is private to the configured user. No RX data is transmitted.
SQLite access is serialized because receiver, web and desktop share it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import threading
import time

from aprs_sqlite_batch import SQLiteBatcher


class APRSArchive:
    def __init__(self, filename, retention_days=30, max_rows=100000):
        self.filename = Path(filename)
        self.filename.parent.mkdir(parents=True, exist_ok=True)
        self.retention_days = int(retention_days)
        self.max_rows = int(max_rows)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.filename, timeout=10, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._since_prune = 0
        self._last_prune = time.monotonic()
        self._pending_total = 0
        self._pending_positions = 0
        self._pending_weather = 0
        self._cached_counts = (0, 0, 0)
        self._counts_dirty = True
        with self.lock, self.db:
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA synchronous=NORMAL')
            self.db.execute('PRAGMA wal_autocheckpoint=1000')
            self.db.execute('''CREATE TABLE IF NOT EXISTS packets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at TEXT NOT NULL, source TEXT NOT NULL,
                destination TEXT NOT NULL, path TEXT NOT NULL,
                kind TEXT NOT NULL, summary TEXT NOT NULL,
                lat REAL, lon REAL, direct INTEGER,
                ax25_hex TEXT NOT NULL, weather INTEGER NOT NULL DEFAULT 0)''')
            self.db.execute('CREATE INDEX IF NOT EXISTS ix_packets_time ON packets(id DESC)')
            self.db.execute('CREATE INDEX IF NOT EXISTS ix_packets_source ON packets(source, id DESC)')
            self.db.execute('''CREATE TABLE IF NOT EXISTS weather (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at TEXT NOT NULL, source TEXT NOT NULL,
                temperature_c REAL, wind_direction_deg REAL,
                wind_kmh REAL, gust_kmh REAL, rain_1h_mm REAL,
                rain_24h_mm REAL, rain_midnight_mm REAL,
                humidity_pct REAL, pressure_hpa REAL,
                FOREIGN KEY(id) REFERENCES packets(id))''')
            self.db.execute('CREATE INDEX IF NOT EXISTS ix_weather_source ON weather(source,id DESC)')
        self.batch = SQLiteBatcher(self._write_batch, name='aprs-history-sqlite',
                                   batch_size=100, flush_seconds=10, max_pending=1000)

    def add(self, packet, weather=None):
        """Queue immutable packet data; never write to disk on the RX path."""
        if packet.simulated or packet.source == '?' or not packet.raw_ax25:
            return
        now = datetime.now(timezone.utc).isoformat(timespec='seconds')
        record = (now, packet.source[:16], packet.destination[:16], packet.path[:120],
                  packet.kind[:50], packet.summary[:240], packet.latitude, packet.longitude,
                  None if packet.heard_direct is None else int(packet.heard_direct),
                  packet.raw_ax25[:1024].hex(), 1 if weather else 0)
        wx = None
        if weather:
            wx = (now, packet.source[:16], weather.get('temperature_c'),
                  weather.get('wind_direction_deg'), weather.get('wind_kmh'),
                  weather.get('gust_kmh'), weather.get('rain_1h_mm'),
                  weather.get('rain_24h_mm'), weather.get('rain_midnight_mm'),
                  weather.get('humidity_pct'), weather.get('pressure_hpa'))
        with self.lock:
            if not self.batch.add((record, wx)):
                raise OSError('APRS SQLite RAM queue full; frame history not stored')
            self._pending_total += 1
            self._pending_positions += int(packet.latitude is not None and packet.longitude is not None)
            self._pending_weather += int(wx is not None)

    def _write_batch(self, records):
        """One atomic transaction per 100 records; weather shares the packet ID."""
        with self.lock:
            with self.db:
                for packet, weather in records:
                    row = self.db.execute(
                        'INSERT INTO packets (received_at,source,destination,path,kind,summary,'
                        'lat,lon,direct,ax25_hex,weather) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                        packet)
                    if weather is not None:
                        self.db.execute(
                            'INSERT INTO weather (id,received_at,source,temperature_c,'
                            'wind_direction_deg,wind_kmh,gust_kmh,rain_1h_mm,'
                            'rain_24h_mm,rain_midnight_mm,humidity_pct,pressure_hpa)'
                            ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                            (row.lastrowid, *weather))
                self._since_prune += len(records)
                if (self._since_prune >= 1000 or
                        time.monotonic() - self._last_prune >= 3600):
                    self._prune_locked()
                    self._since_prune = 0
                    self._last_prune = time.monotonic()
            # Only update RAM counters AFTER the SQLite commit succeeded.
            self._pending_total -= len(records)
            self._pending_positions -= sum(
                p[6] is not None and p[7] is not None for p, _ in records)
            self._pending_weather -= sum(w is not None for _, w in records)
            self._counts_dirty = True

    def _prune_locked(self):
        cutoff = (datetime.now(timezone.utc)-timedelta(days=self.retention_days)).isoformat(timespec='seconds')
        self.db.execute('DELETE FROM packets WHERE received_at < ?', (cutoff,))
        self.db.execute('''DELETE FROM packets WHERE id <= COALESCE((
            SELECT id FROM packets ORDER BY id DESC LIMIT 1 OFFSET ?), 0)''', (self.max_rows,))
        self.db.execute('DELETE FROM weather WHERE id NOT IN (SELECT id FROM packets)')

    def prune(self):
        """Manual/startup retention: drain pending rows before pruning."""
        self.batch.flush(timeout=15)
        with self.lock, self.db:
            self._prune_locked()
            self._since_prune = 0
            self._last_prune = time.monotonic()
            self._counts_dirty = True

    @staticmethod
    def _limit(value, maximum=500):
        try:
            number = int(value)
        except (ValueError, TypeError):
            raise ValueError('Invalid archive limit')
        if not 1 <= number <= maximum:
            raise ValueError('Archive limit outside permitted range')
        return number

    def packets(self, limit=100, source=''):
        # On-demand history reads should include just-received frames.
        self.batch.flush(timeout=10)
        count = self._limit(limit)
        source = str(source).upper().strip()
        if len(source) > 16:
            raise ValueError('Invalid callsign length')
        with self.lock:
            if source:
                rows = self.db.execute('''SELECT id,received_at,source,destination,path,
                    kind,summary,lat,lon,direct,weather FROM packets
                    WHERE source LIKE ? ORDER BY id DESC LIMIT ?''', ('%'+source+'%',count))
            else:
                rows = self.db.execute('''SELECT id,received_at,source,destination,path,
                    kind,summary,lat,lon,direct,weather FROM packets
                    ORDER BY id DESC LIMIT ?''', (count,))
            return [dict(row) for row in rows.fetchall()]

    def positions(self, source, limit=300):
        self.batch.flush(timeout=10)
        count = self._limit(limit, 1000)
        source = str(source).strip().upper()
        if not 1 <= len(source) <= 16 or not all(x.isalnum() or x == '-' for x in source):
            raise ValueError('Invalid callsign')
        with self.lock:
            rows = self.db.execute('''SELECT received_at,lat,lon,direct FROM packets
                WHERE source=? AND lat IS NOT NULL AND lon IS NOT NULL
                ORDER BY id DESC LIMIT ?''', (source,count))
            return list(reversed([dict(row) for row in rows.fetchall()]))

    def weather_rows(self, source='', limit=100):
        self.batch.flush(timeout=10)
        count = self._limit(limit)
        source = str(source).strip().upper()
        if len(source) > 16:
            raise ValueError('Invalid weather source')
        with self.lock:
            if source:
                rows = self.db.execute('SELECT * FROM weather WHERE source LIKE ? ORDER BY id DESC LIMIT ?',
                                       ('%'+source+'%',count))
            else:
                rows = self.db.execute('SELECT * FROM weather ORDER BY id DESC LIMIT ?', (count,))
            return [dict(row) for row in rows.fetchall()]

    def summary(self):
        """Cheap service-health counts. Never forces a disk write."""
        with self.lock:
            if self._counts_dirty:
                total = self.db.execute('SELECT count(*) FROM packets').fetchone()[0]
                positioned = self.db.execute(
                    'SELECT count(*) FROM packets WHERE lat IS NOT NULL AND lon IS NOT NULL').fetchone()[0]
                weather = self.db.execute('SELECT count(*) FROM weather').fetchone()[0]
                self._cached_counts = (total, positioned, weather)
                self._counts_dirty = False
            total, positioned, weather = self._cached_counts
            batch_stats = self.batch.stats()
            return {'packets': total + self._pending_total,
                    'positions': positioned + self._pending_positions,
                    'weather': weather + self._pending_weather,
                    'retention_days': self.retention_days, 'max_rows': self.max_rows,
                    'path': str(self.filename), 'storage': batch_stats}

    def flush(self, timeout=10):
        self.batch.flush(timeout=timeout)

    def close(self):
        self.batch.close(timeout=15)
        with self.lock:
            self.db.close()
