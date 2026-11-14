"""APRS operations: bounded durable packet journal, object generator and portable backup.

Never transmit on module import. RF transmissions require user confirmation in the service.
"""
from __future__ import annotations
import copy
import datetime as dt
import json
import logging
import re
import sqlite3
import threading
from pathlib import Path
from aprs_station import aprs_coord, decimal_coordinate
from aprs_messages import normalize_path
from service_config import validate_config
from aprs_sqlite_batch import SQLiteBatcher

NAME_RE = re.compile(r'^[A-Za-z0-9 _.-]{1,9}$')
PRINTABLE = re.compile(r'^[\x20-\x7e]{0,43}$')


def object_payload(name: str, lat: float, lon: float, comment: str = '', alive=True,
                   symbol_table='/', symbol='r', now=None) -> str:
    """APRS 1.0.1 object, UTC DDHHMMz timestamp, live '*' or killed '_'."""
    if not isinstance(name, str) or not NAME_RE.fullmatch(name) or not name.strip():
        raise ValueError('Název objektu: 1 až 9 ASCII znaků, písmena/číslice/mezera/_/.-')
    if not isinstance(comment, str) or not PRINTABLE.fullmatch(comment):
        raise ValueError('Komentář objektu: maximálně 43 znaků ASCII.')
    if symbol_table not in ('/', '\\') or not isinstance(symbol,str) or len(symbol) != 1 or not (33 <= ord(symbol) <= 126):
        raise ValueError('Neplatná tabulka nebo APRS symbol objektu.')
    lat, lon = decimal_coordinate(lat, True), decimal_coordinate(lon, False)
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Čas objektu musí obsahovat časové pásmo.')
    stamp = now.astimezone(dt.timezone.utc).strftime('%d%H%Mz')
    return ';' + name.upper().ljust(9) + ('*' if alive else '_') + stamp + aprs_coord(lat,True) + symbol_table + aprs_coord(lon,False) + symbol + comment


def validate_object_request(req: dict) -> dict:
    if not isinstance(req, dict):
        raise ValueError('Neplatné nastavení objektu.')
    name=req.get('name','')
    if not isinstance(name,str) or not NAME_RE.fullmatch(name) or not name.strip():
        raise ValueError('Název objektu je neplatný.')
    return dict(name=name.upper().strip(), lat=decimal_coordinate(req.get('lat'),True),
                lon=decimal_coordinate(req.get('lon'),False), comment=req.get('comment',''),
                path=normalize_path(req.get('path','WIDE1-1')),
                alive=req.get('alive',True) is True,
                symbol_table=req.get('symbol_table','/'),symbol=req.get('symbol','r'))


class Journal:
    """Persist service events in bounded asynchronous SQLite batches.

    Requesting a manual read flushes the queue first; ordinary RX/TX logging
    stays in RAM and does not commit each received packet to the SD card.
    """
    def __init__(self, path: Path, max_rows=20000):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.con=sqlite3.connect(self.path,timeout=5,check_same_thread=False)
        self.lock=threading.RLock()
        with self.lock, self.con:
            self.con.execute('PRAGMA journal_mode=WAL')
            self.con.execute('PRAGMA synchronous=NORMAL')
            self.con.execute('PRAGMA wal_autocheckpoint=1000')
            self.con.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, utc TEXT NOT NULL, category TEXT NOT NULL, outcome TEXT NOT NULL, source TEXT, target TEXT, detail TEXT)')
            self.con.execute('CREATE INDEX IF NOT EXISTS idx_events_category ON events(category,id)')
        self.max_rows=max_rows
        self.count=0
        self._since_prune=0
        self.batch=SQLiteBatcher(self._write_batch, name='aprs-operations-sqlite',
                                 batch_size=100, flush_seconds=10, max_pending=1000)

    def log(self, category, outcome, source='', target='', detail=''):
        record=(dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
                str(category)[:24],str(outcome)[:32],str(source)[:24],
                str(target)[:24],str(detail)[:250])
        try:
            if not self.batch.add(record):
                drops=self.batch.stats()['dropped']
                if drops==1 or drops%100==0:
                    logging.getLogger('ok5tvr.aprs').warning(
                        'Operations journal RAM queue full; %d events dropped',drops)
            else:
                self.count+=1
        except RuntimeError as exc:
            # Logging failures must not stop USB KISS / iGate / DIGI.
            logging.getLogger('ok5tvr.aprs').warning('Provozní deník nelze zapsat: %s',exc)

    def _write_batch(self, records):
        with self.lock, self.con:
            self.con.executemany(
                'INSERT INTO events(utc,category,outcome,source,target,detail) VALUES(?,?,?,?,?,?)',
                records)
            self._since_prune += len(records)
            if self._since_prune >= 1000:
                self.con.execute(
                    'DELETE FROM events WHERE id <= (SELECT MAX(id)-? FROM events)',
                    (self.max_rows,))
                self._since_prune=0

    def read(self,limit=100,category=''):
        limit=min(max(int(limit),1),500)
        # The journal is normally read on demand. Include the most recent
        # events without changing the periodic 10s writer schedule.
        self.batch.flush(timeout=10)
        with sqlite3.connect(self.path,timeout=5) as db:
            db.row_factory=sqlite3.Row
            if category:
                rows=db.execute(
                    'SELECT * FROM events WHERE category=? ORDER BY id DESC LIMIT ?',
                    (category,limit)).fetchall()
            else:
                rows=db.execute(
                    'SELECT * FROM events ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return [dict(r) for r in rows]

    def stats(self):
        return self.batch.stats()

    def close(self):
        self.batch.close(timeout=15)
        with self.lock:
            self.con.close()


def backup_document(config, include_secrets=False):
    """Export portable JSON, never automatically include passwords or URL bearer tokens."""
    data=copy.deepcopy(config.data)
    # Autostart is intentionally reset on restore, even from a local backup.
    data['digi']['autostart']=False
    data['igate']['autostart']=False
    data['messages']['auto_ack']=False
    return {'format':'ok5tvr-config','version':1,'exported_at':dt.datetime.now(dt.timezone.utc).isoformat(),
            'config':data,'includes_credentials':False}


def validate_restore_document(doc):
    if not isinstance(doc,dict) or doc.get('format')!='ok5tvr-config' or doc.get('version')!=1 or not isinstance(doc.get('config'),dict):
        raise ValueError('Nepodporovaný nebo neplatný formát zálohy.')
    if len(json.dumps(doc))>32768:
        raise ValueError('Záloha překračuje bezpečný limit 32 kB.')
    config=validate_config(doc['config'])
    config['digi']['autostart']=False
    config['igate']['autostart']=False
    config['messages']['auto_ack']=False
    return config
