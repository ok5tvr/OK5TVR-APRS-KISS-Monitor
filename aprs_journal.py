"""Bounded, persistent APRS operations journal. No passwords or admin URLs.

Each row is recorded as a *host observation*: 'USB written' never claims
that the radio successfully radiated a frame. Valid packet details limited.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
from pathlib import Path
import sqlite3
import threading

DIRECTIONS = {'RX', 'TX', 'IS', 'DROP', 'SYSTEM'}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def clean_text(value, limit=240):
    return str(value if value is not None else '').replace('\r', ' ').replace('\n', ' ').replace('\x00', '')[:limit]


class OperationsJournal:
    def __init__(self, filename: str | Path, keep=20000):
        self.file = Path(filename)
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.keep = keep
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.file, check_same_thread=False, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.count_since_prune = 0
        with self.lock, self.db:
            self.db.execute('''CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
                direction TEXT NOT NULL, subsystem TEXT NOT NULL,
                source TEXT NOT NULL, destination TEXT NOT NULL,
                path TEXT NOT NULL, detail TEXT NOT NULL, outcome TEXT NOT NULL)''')
            self.db.execute('CREATE INDEX IF NOT EXISTS ix_events_time ON events(id DESC)')

    def add(self, direction, subsystem, source='', destination='', path='', detail='', outcome=''):
        if direction not in DIRECTIONS:
            raise ValueError('Invalid journal direction')
        record = (utcnow(), direction, clean_text(subsystem, 24), clean_text(source, 14),
                  clean_text(destination, 14), clean_text(path, 100),
                  clean_text(detail, 240), clean_text(outcome, 110))
        with self.lock, self.db:
            self.db.execute('''INSERT INTO events
                (at,direction,subsystem,source,destination,path,detail,outcome)
                VALUES (?,?,?,?,?,?,?,?)''', record)
            self.count_since_prune += 1
            if self.count_since_prune >= 250:
                self.db.execute('''DELETE FROM events WHERE id <=
                    COALESCE((SELECT id FROM events ORDER BY id DESC LIMIT 1 OFFSET ?),0)''',
                    (self.keep,))
                self.count_since_prune = 0

    def recent(self, limit=250, direction=''):
        if type(limit) is not int or not 1 <= limit <= 2000:
            raise ValueError('Log: limit 1–2000')
        if direction and direction not in DIRECTIONS:
            raise ValueError('Neplatný filtr provozního deníku')
        with self.lock:
            sql = 'SELECT * FROM events'
            args = []
            if direction:
                sql += ' WHERE direction=?'
                args.append(direction)
            sql += ' ORDER BY id DESC LIMIT ?'
            args.append(limit)
            return [dict(x) for x in self.db.execute(sql, args).fetchall()]

    def csv_export(self, limit=2000) -> bytes:
        rows = list(reversed(self.recent(limit)))
        data = io.StringIO(newline='')
        writer = csv.writer(data)
        keys = ('id', 'at', 'direction', 'subsystem', 'source', 'destination', 'path', 'detail', 'outcome')
        writer.writerow(keys)
        for row in rows:
            # Prevent spreadsheet formula injection; public RF payload can start with =,+,-,@.
            writer.writerow([("'" + str(row[k]) if isinstance(row[k], str) and row[k].lstrip()[:1] in ('=', '+', '-', '@')
                              else row[k]) for k in keys])
        return data.getvalue().encode('utf-8-sig')

    def clear(self):
        with self.lock, self.db:
            self.db.execute('DELETE FROM events')
            self.count_since_prune = 0

    def count(self):
        with self.lock:
            return self.db.execute('SELECT count(*) FROM events').fetchone()[0]

    def close(self):
        with self.lock:
            self.db.close()
