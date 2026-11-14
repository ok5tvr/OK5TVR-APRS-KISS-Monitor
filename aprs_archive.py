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


class APRSArchive:
    def __init__(self, filename, retention_days=30, max_rows=100000):
        self.filename = Path(filename)
        self.filename.parent.mkdir(parents=True, exist_ok=True)
        self.retention_days = int(retention_days)
        self.max_rows = int(max_rows)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.filename, timeout=10, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.insertions = 0
        with self.lock, self.db:
            self.db.execute('PRAGMA journal_mode=WAL')
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

    def add(self, packet, weather=None):
        if packet.simulated or packet.source == '?' or not packet.raw_ax25:
            return
        now = datetime.now(timezone.utc).isoformat(timespec='seconds')
        with self.lock, self.db:
            cursor = self.db.execute('''INSERT INTO packets
                (received_at,source,destination,path,kind,summary,lat,lon,direct,ax25_hex,weather)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (
                    now, packet.source[:16], packet.destination[:16], packet.path[:120],
                    packet.kind[:50], packet.summary[:240], packet.latitude, packet.longitude,
                    None if packet.heard_direct is None else int(packet.heard_direct),
                    packet.raw_ax25[:1024].hex(), 1 if weather else 0))
            if weather:
                self.db.execute('''INSERT INTO weather
                    (id,received_at,source,temperature_c,wind_direction_deg,wind_kmh,
                     gust_kmh,rain_1h_mm,rain_24h_mm,rain_midnight_mm,humidity_pct,pressure_hpa)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', (
                    cursor.lastrowid, now, packet.source[:16],
                    weather.get('temperature_c'), weather.get('wind_direction_deg'),
                    weather.get('wind_kmh'), weather.get('gust_kmh'),
                    weather.get('rain_1h_mm'), weather.get('rain_24h_mm'),
                    weather.get('rain_midnight_mm'), weather.get('humidity_pct'),
                    weather.get('pressure_hpa')))
            self.insertions += 1
            if self.insertions % 250 == 0:
                self._prune_locked()

    def _prune_locked(self):
        cutoff = (datetime.now(timezone.utc)-timedelta(days=self.retention_days)).isoformat(timespec='seconds')
        self.db.execute('DELETE FROM packets WHERE received_at < ?', (cutoff,))
        self.db.execute('''DELETE FROM packets WHERE id <= COALESCE((
            SELECT id FROM packets ORDER BY id DESC LIMIT 1 OFFSET ?), 0)''', (self.max_rows,))
        self.db.execute('DELETE FROM weather WHERE id NOT IN (SELECT id FROM packets)')

    def prune(self):
        with self.lock, self.db:
            self._prune_locked()

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
        with self.lock:
            packets = self.db.execute('SELECT count(*) FROM packets').fetchone()[0]
            positions = self.db.execute('SELECT count(*) FROM packets WHERE lat IS NOT NULL').fetchone()[0]
            weather = self.db.execute('SELECT count(*) FROM weather').fetchone()[0]
            return {'packets': packets, 'positions': positions, 'weather': weather,
                    'retention_days': self.retention_days, 'max_rows': self.max_rows,
                    'path': str(self.filename)}

    def close(self):
        with self.lock:
            self.db.close()
