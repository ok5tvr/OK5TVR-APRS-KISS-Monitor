"""APRS addressed messages over local RF KISS (not APRS-IS -> RF).

APRS101 §14: :ADDRESSEE9:MESSAGE{ID, :ADDRESSEE9:ackID/rejID.
Messages are public amateur-radio transmissions, *not* private chat.

All mutable state is serialized by APRSService's event loop; database reads from
HTTP handlers use a lock. Restart never resumes unattended message transmissions.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from aprs_features import CALL_RE, encode_kiss_data, encode_ui_packet

ID_RE = re.compile(r'^[A-Za-z0-9]{1,5}$')
TEXT_RE = re.compile(r'^[\x20-\x7E]{1,67}$')
# Minimal useful RF paths. Reject Internet-only and oversized WIDEn-N paths.
HOP_RE = re.compile(r'^(?:WIDE1-1|WIDE2-[12]|[A-Z0-9]{3,6}(?:-(?:[1-9]|1[0-5]))?)$')
BAD_HOPS = {'TCPIP', 'TCPXX', 'NOGATE', 'RFONLY', 'APRS', 'TRACE', 'RELAY', 'WIDE', 'I'}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def normalize_call(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('Značka musí být text.')
    call = value.strip().upper()
    if not CALL_RE.fullmatch(call):
        raise ValueError('Neplatná volací značka / SSID (např. OK5XYZ-9).')
    return call


def normalize_path(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('RF cesta musí být text.')
    value = value.strip().upper()
    if value in ('', 'DIRECT', 'NONE'):
        return ''
    hops = [hop.strip() for hop in value.split(',')]
    if not 1 <= len(hops) <= 2 or len(set(hops)) != len(hops):
        raise ValueError('RF cesta: maximálně dva různé hop(y), oddělené čárkou.')
    for hop in hops:
        if (not HOP_RE.fullmatch(hop) or hop in BAD_HOPS or hop.startswith(('QA','TRACE'))
                or (hop.startswith('WIDE') and hop not in {'WIDE1-1','WIDE2-1','WIDE2-2'})):
            raise ValueError('Nepovolená RF cesta. Použij DIRECT, WIDE1-1 nebo WIDE1-1,WIDE2-1.')
    return ','.join(hops)


def validate_body(value: str) -> str:
    if not isinstance(value, str) or not TEXT_RE.fullmatch(value) or '{' in value or '}' in value:
        raise ValueError('Zpráva musí mít 1–67 ASCII znaků bez diakritiky a znaků { nebo }.')
    return value


def message_info(target: str, text: str, identifier: str | None = None) -> str:
    target = normalize_call(target)
    validate_body(text)
    if identifier is not None and not ID_RE.fullmatch(identifier):
        raise ValueError('Neplatné ID zprávy.')
    return ':' + target.ljust(9) + ':' + text + ('{' + identifier if identifier else '')


def ack_info(target: str, identifier: str, reject: bool = False) -> str:
    target = normalize_call(target)
    if not ID_RE.fullmatch(identifier):
        raise ValueError('Neplatné ACK ID.')
    return ':' + target.ljust(9) + ':' + ('rej' if reject else 'ack') + identifier


def parse_message(info: bytes) -> dict | None:
    """Only addressed APRS messages. Do not mistake bulletins or status for chat."""
    if not isinstance(info, bytes) or len(info) < 12 or info[:1] != b':' or info[10:11] != b':':
        return None
    try:
        target = info[1:10].decode('ascii').strip().upper()
        if not CALL_RE.fullmatch(target) or target.startswith('BLN'):
            return None
        raw = info[11:]
        # ack/rej are a special case without the '{' separator.
        ar = re.fullmatch(rb'(ack|rej)([A-Za-z0-9]{1,5})', raw, flags=re.I)
        if ar:
            return {'target': target, 'kind': ar[1].decode().lower(),
                    'id': ar[2].decode('ascii'), 'text': '', 'reply_ack': None}
        # APRS 1.1 reply-ack format: {NN}AA, total ID portion <=5 chars.
        text, sep, suffix = raw.rpartition(b'{')
        msgid, reply_ack = None, None
        if sep:
            parts = suffix.split(b'}', 1)
            if len(parts) == 1 and ID_RE.fullmatch(parts[0].decode('ascii')):
                msgid = parts[0].decode('ascii')
            elif (len(parts) == 2 and len(suffix) <= 5 and
                  1 <= len(parts[0]) <= 2 and 1 <= len(parts[1]) <= 2 and
                  ID_RE.fullmatch(parts[0].decode('ascii')) and
                  ID_RE.fullmatch(parts[1].decode('ascii'))):
                msgid, reply_ack = parts[0].decode('ascii'), parts[1].decode('ascii')
            else:
                return None
        else:
            text = raw
        if len(text) > 67 or not text:
            return None
        decoded = text.decode('latin-1')
        return {'target': target, 'kind': 'message', 'id': msgid,
                'text': decoded, 'reply_ack': reply_ack}
    except (UnicodeDecodeError, ValueError):
        return None


class MessageManager:
    """SQLite message history, matching ACKs, strictly bounded RF TX/retry."""

    def __init__(self, db_path: str | Path, own_call: str, path='WIDE1-1',
                 auto_ack=False, retry_seconds=45, max_attempts=3):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Restrict only the application's own config directory. A custom
        # --config may intentionally be in /opt or a shared directory.
        if os.name != 'nt' and self.db_path.parent.name == 'ok5tvr-aprs':
            os.chmod(self.db_path.parent, 0o700)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.db_path, check_same_thread=False, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.ack_queue: list[dict] = []
        self.ack_last: dict[tuple, float] = {}
        self._last_tx_at = float('-inf')
        self.configure(own_call, path, auto_ack, retry_seconds, max_attempts)
        with self.lock, self.db:
            self.db.execute('''CREATE TABLE IF NOT EXISTS inbox (
                id INTEGER PRIMARY KEY, arrived_at TEXT NOT NULL, last_seen REAL NOT NULL,
                sender TEXT NOT NULL, recipient TEXT NOT NULL, text TEXT NOT NULL,
                message_id TEXT, path TEXT NOT NULL, duplicates INTEGER NOT NULL DEFAULT 0,
                ack_sent INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT 'RF')''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                sender TEXT NOT NULL, recipient TEXT NOT NULL, text TEXT NOT NULL,
                message_id TEXT NOT NULL, path TEXT NOT NULL, status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
                next_retry REAL NOT NULL DEFAULT 0, last_error TEXT NOT NULL DEFAULT '')''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY, value TEXT NOT NULL)''')
            # A process restart must NOT unexpectedly restart automatic RF TX.
            self.db.execute("UPDATE outbox SET status='interrupted', updated_at=? "
                            "WHERE status IN ('queued','usb_queued','waiting_ack')", (utc_now(),))
        if os.name != 'nt':
            os.chmod(self.db_path, 0o600)

    def configure(self, own_call, path, auto_ack=False, retry_seconds=45, max_attempts=3):
        self.own_call = normalize_call(own_call)
        self.default_path = normalize_path(path)
        if type(auto_ack) is not bool or type(retry_seconds) is not int or type(max_attempts) is not int:
            raise ValueError('Neplatné parametry zpráv.')
        if not 30 <= retry_seconds <= 180 or not 1 <= max_attempts <= 5:
            raise ValueError('Opakování zpráv mimo povolené limity.')
        self.auto_ack = auto_ack
        self.retry_seconds = retry_seconds
        self.max_attempts = max_attempts

    def close(self):
        with self.lock:
            self.db.close()

    def snapshot(self, count=150):
        with self.lock:
            inbox = [dict(v) for v in self.db.execute('''SELECT id,arrived_at,sender,recipient,text,
              message_id,path,duplicates,ack_sent,source FROM inbox ORDER BY id DESC LIMIT ?''', (count,))]
            outbox = [dict(v) for v in self.db.execute('''SELECT id,created_at,updated_at,sender,recipient,text,
              message_id,path,status,attempts,max_attempts,last_error FROM outbox ORDER BY id DESC LIMIT ?''', (count,))]
            stats = {'inbox': self.db.execute('SELECT COUNT(*) FROM inbox').fetchone()[0],
                     'outbox': self.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],
                     'pending': self.db.execute('''SELECT COUNT(*) FROM outbox
                       WHERE status IN ('queued','usb_queued','waiting_ack')''').fetchone()[0]}
        return {'call': self.own_call, 'default_path': self.default_path,
                'auto_ack': self.auto_ack, 'retry_seconds': self.retry_seconds,
                'max_attempts': self.max_attempts, 'stats': stats,
                'inbox': inbox, 'outbox': outbox}

    def _next_id(self):
        # 3-digit rotating ID stored on disk; avoid in-flight IDs for the same own call.
        with self.lock:
            row = self.db.execute("SELECT value FROM meta WHERE key='message_serial'").fetchone()
            previous = int(row['value']) if row else 0
            for increment in range(1,1000):
                num = (previous + increment - 1) % 999 + 1
                candidate = f'{num:03d}'
                exists = self.db.execute('''SELECT 1 FROM outbox
                  WHERE sender=? AND message_id=? AND status IN ('queued','usb_queued','waiting_ack')''',
                  (self.own_call,candidate)).fetchone()
                if not exists:
                    self.db.execute("INSERT INTO meta(key,value) VALUES('message_serial',?) "
                                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(num),))
                    return candidate
        raise ValueError('Vyčerpána ID zpráv; počkej na dokončení předchozích.')

    def compose(self, target: str, body: str, path: str | None = None) -> dict:
        dest = normalize_call(target)
        if dest == self.own_call:
            raise ValueError('Není možné posílat zprávu na vlastní volací značku.')
        body = validate_body(body)
        rf_path = normalize_path(self.default_path if path is None else path)
        with self.lock, self.db:
            pending = self.db.execute("SELECT COUNT(*) FROM outbox WHERE status IN ('queued','usb_queued','waiting_ack')").fetchone()[0]
            if pending >= 10:
                raise ValueError('Nejdřív dokonči nebo zruš čekající zprávy (limit 10).')
            msg_id = self._next_id()
            timestamp = utc_now()
            cursor = self.db.execute('''INSERT INTO outbox
                (created_at,updated_at,sender,recipient,text,message_id,path,status,max_attempts)
                VALUES (?,?,?,?,?,?,?,?,?)''', (timestamp,timestamp,self.own_call,dest,
                                          body,msg_id,rf_path,'queued',self.max_attempts))
            self._prune('outbox', 500)
            return {'id': cursor.lastrowid, 'message_id': msg_id,
                    'recipient': dest, 'path': rf_path, 'status': 'queued'}

    def _prune(self, table, limit=500):
        # Never drop pending replies/outgoing retries when pruning bounded history.
        if table == 'outbox':
            self.db.execute('''DELETE FROM outbox WHERE id IN
              (SELECT id FROM outbox WHERE status NOT IN ('queued','usb_queued','waiting_ack')
               ORDER BY id DESC LIMIT -1 OFFSET ?)''', (limit,))
        else:
            self.db.execute('''DELETE FROM inbox WHERE id IN
              (SELECT id FROM inbox ORDER BY id DESC LIMIT -1 OFFSET ?)''', (limit,))

    def cancel(self, identifier: int) -> str:
        if type(identifier) is not int or identifier < 1:
            raise ValueError('Neplatné číslo zprávy.')
        with self.lock, self.db:
            row = self.db.execute('SELECT status FROM outbox WHERE id=?', (identifier,)).fetchone()
            if row is None:
                raise ValueError('Zpráva nenalezena.')
            if row['status'] not in ('queued','usb_queued','waiting_ack'):
                return 'Zpráva již není ve frontě.'
            self.db.execute("UPDATE outbox SET status='cancelled', updated_at=? WHERE id=?", (utc_now(),identifier))
        return 'Opakování zprávy zastaveno. Pokud již byla ve frontě USB, odeslání nelze vzít zpět.'

    def acknowledge_manual(self, identifier: int, reject: bool = False) -> str:
        if type(identifier) is not int or identifier < 1:
            raise ValueError('Neplatné číslo zprávy.')
        with self.lock:
            row = self.db.execute('SELECT id,sender,message_id FROM inbox WHERE id=?',
                                  (identifier,)).fetchone()
        if row is None or not row['message_id']:
            raise ValueError('Zpráva neexistuje nebo neobsahuje identifikátor pro ACK.')
        if len(self.ack_queue) >= 20:
            raise ValueError('Fronta potvrzení ACK je zaplněná.')
        self.ack_queue.append({'inbox_id':identifier,'target':row['sender'],
                               'message_id':row['message_id'], 'reject':reject})
        return ('REJ' if reject else 'ACK') + ' zařazeno do RF fronty. Zápis do TNC ověř v počítadle RX/TX.'

    def _acknowledge_outgoing(self, from_call: str, msgid: str, kind: str) -> bool:
        with self.lock, self.db:
            row = self.db.execute('''SELECT id FROM outbox WHERE sender=? AND recipient=? AND message_id=?
              AND status IN ('queued','usb_queued','waiting_ack') ORDER BY id DESC LIMIT 1''',
              (self.own_call,from_call,msgid)).fetchone()
            if row is None:
                return False
            self.db.execute('UPDATE outbox SET status=?,updated_at=?,next_retry=0 WHERE id=?',
                            ('ack' if kind == 'ack' else 'rej', utc_now(), row['id']))
        return True

    def receive(self, packet, radio_ready: bool) -> dict | None:
        if getattr(packet,'simulated',False) or packet.control != 0x03 or packet.pid != 0xF0:
            return None
        decoded = parse_message(packet.raw_info)
        if decoded is None or decoded['target'] != self.own_call:
            return None
        try:
            from_call = normalize_call(packet.source)
        except ValueError:
            return None
        if from_call == self.own_call:
            return None
        if decoded['kind'] in ('ack','rej'):
            matched = self._acknowledge_outgoing(from_call, decoded['id'], decoded['kind'])
            return {'kind':decoded['kind'], 'matched':matched, 'from':from_call,
                    'message_id':decoded['id']}
        if decoded['reply_ack']:
            self._acknowledge_outgoing(from_call, decoded['reply_ack'], 'ack')
        now = time.time()
        with self.lock, self.db:
            match = None
            if decoded['id']:
                match = self.db.execute('''SELECT id FROM inbox WHERE sender=? AND recipient=?
                  AND message_id=? AND text=? AND last_seen>? ORDER BY id DESC LIMIT 1''',
                  (from_call,self.own_call,decoded['id'],decoded['text'],now-900)).fetchone()
            if match:
                self.db.execute('UPDATE inbox SET duplicates=duplicates+1,last_seen=? WHERE id=?',
                                (now,match['id']))
                inbox_id = match['id']; duplicate = True
            else:
                cursor = self.db.execute('''INSERT INTO inbox
                  (arrived_at,last_seen,sender,recipient,text,message_id,path)
                  VALUES (?,?,?,?,?,?,?)''',
                  (utc_now(),now,from_call,self.own_call,decoded['text'],decoded['id'],packet.path))
                inbox_id = cursor.lastrowid; duplicate = False
                self._prune('inbox', 500)
        if decoded['id'] and self.auto_ack and radio_ready:
            key = (from_call, decoded['id'])
            if now - self.ack_last.get(key, 0) >= 45 and len(self.ack_queue) < 20:
                self.ack_queue.append({'inbox_id': inbox_id, 'target': from_call,
                                       'message_id': decoded['id']})
                self.ack_last[key] = now
            if len(self.ack_last) > 1000:
                self.ack_last = {key:t for key,t in self.ack_last.items() if now-t < 900}
        return {'kind':'message','from':from_call,'duplicate':duplicate,
                'message_id':decoded['id'],'inbox_id':inbox_id}

    def tx_tick(self, reader, radio_ready: bool) -> str | None:
        """At most one queued frame per interval; no TX without a working USB reader.

        Refuse automatic ACK until explicitly opted-in in persisted config.
        """
        if not radio_ready or reader is None or time.monotonic()-self._last_tx_at < 8:
            return None
        # Queue ACK first so distant stations need fewer retries.
        if self.ack_queue:
            item = self.ack_queue[0]
            frame = encode_ui_packet(self.own_call, 'APRS', self.default_path,
                                     ack_info(item['target'],item['message_id'],item.get('reject', False)))
            if reader.send(encode_kiss_data(frame), category=f'msgack:{item["inbox_id"]}'):
                self.ack_queue.pop(0)
                self._last_tx_at = time.monotonic()
                return 'ACK'
            return None
        now = time.time()
        with self.lock:
            row = self.db.execute('''SELECT * FROM outbox WHERE status IN ('queued','waiting_ack')
                AND next_retry<=? ORDER BY id LIMIT 1''', (now,)).fetchone()
            if row is None:
                return None
            if row['status'] == 'waiting_ack' and row['attempts'] >= row['max_attempts']:
                with self.db:
                    self.db.execute("UPDATE outbox SET status='failed',updated_at=? WHERE id=?",
                                    (utc_now(),row['id']))
                return 'failed'
            frame = encode_ui_packet(row['sender'], 'APRS', row['path'],
                                     message_info(row['recipient'],row['text'],row['message_id']))
            if reader.send(encode_kiss_data(frame), category=f'msg:{row["id"]}'):
                with self.db:
                    self.db.execute("UPDATE outbox SET status='usb_queued',updated_at=? WHERE id=?",
                                    (utc_now(),row['id']))
                self._last_tx_at = time.monotonic()
                return 'message'
        return None

    def tx_written(self, category: str):
        if category.startswith('msgack:'):
            with self.lock, self.db:
                self.db.execute('UPDATE inbox SET ack_sent=ack_sent+1 WHERE id=?',
                                (int(category[7:]),))
            return
        if category.startswith('msg:'):
            identifier = int(category[4:]); now = time.time()
            with self.lock, self.db:
                row = self.db.execute('SELECT attempts,status FROM outbox WHERE id=?',(identifier,)).fetchone()
                if row is None or row['status'] not in ('usb_queued','cancelled'):
                    return
                if row['status']=='cancelled':
                    return
                attempts = row['attempts'] + 1
                self.db.execute('''UPDATE outbox SET status='waiting_ack',attempts=?,next_retry=?,updated_at=?
                    WHERE id=?''', (attempts,now+self.retry_seconds*attempts,utc_now(),identifier))

    def tx_error(self, category: str, message: str):
        if category.startswith('msg:'):
            identifier = int(category[4:])
            with self.lock, self.db:
                self.db.execute("UPDATE outbox SET status='failed',last_error=?,updated_at=? WHERE id=?",
                                (str(message)[:150],utc_now(),identifier))

    def usb_closed(self):
        # Unsent USB-buffered frames may have been discarded; do not auto TX
        # after reconnect without another explicit operator decision.
        with self.lock, self.db:
            self.db.execute("UPDATE outbox SET status='interrupted', updated_at=? "
                            "WHERE status IN ('queued','usb_queued','waiting_ack')", (utc_now(),))
        self.ack_queue.clear()
