"""Small AX.25 modulo-8 connected-mode personal packet BBS over an external KISS TNC.

Single RF link, stop-and-wait (window=1), direct connections only. This is not
APRS message handling; it handles SABM/UA/I/RR/REJ/DISC/DM frames. All BBS RF
TX is OFF on startup and requires an authenticated operator action.

No FCS is added (KISS firmware handles CRC). No commands execute shell code.
An amateur callsign in AX.25 is NOT cryptographic authentication.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sqlite3
import threading
import time

from aprs_features import CALL_RE, address_bytes, encode_kiss_data

MAX_LINE = 100
MAX_BODY = 800
PACLEN = 96
T1 = 12.0
N2 = 4


def validate_bbs_config(cfg, igate='', digi=''):
    if type(cfg) is not dict:
        raise ValueError('BBS: expected configuration object')
    out = dict(cfg)
    call = out.get('call')
    if not isinstance(call, str) or (call and not CALL_RE.fullmatch(call.upper())):
        raise ValueError('BBS: enter a valid AX.25 callsign or leave blank')
    out['call'] = call.upper()
    if call:
        if out['call'] in (igate.upper(), digi.upper()):
            raise ValueError('BBS must use a separate SSID from IGate and DIGI')
        if igate and out['call'].split('-')[0] != igate.upper().split('-')[0]:
            raise ValueError('BBS callsign must belong to the same licensed operator')
    for key, lower, upper in (('max_messages', 50, 2000),
                              ('idle_seconds', 60, 600),
                              ('max_tx_per_minute', 2, 24)):
        value = out.get(key)
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError(f'BBS {key}: {lower}..{upper} integer required')
    if type(out.get('allow_posts')) is not bool:
        raise ValueError('BBS allow_posts: expected boolean')
    welcome = out.get('welcome')
    if (not isinstance(welcome, str) or len(welcome) > 75 or
            any(ord(c) < 32 or ord(c) > 126 for c in welcome)):
        raise ValueError('BBS welcome: max 75 printable ASCII characters')
    return out


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class BBSStore:
    """Bounded SQLite personal mail + public bulletins; no attachment or forwarding."""
    def __init__(self, path, max_messages=500):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_messages = max_messages
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.lock, self.db:
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA synchronous=NORMAL')
            self.db.execute('''CREATE TABLE IF NOT EXISTS bbs_mail (
                id INTEGER PRIMARY KEY,
                created_utc TEXT NOT NULL,
                sender TEXT NOT NULL, recipient TEXT NOT NULL,
                subject TEXT NOT NULL, body TEXT NOT NULL)''')
            self.db.execute('CREATE INDEX IF NOT EXISTS ix_bbs_to ON bbs_mail(recipient,id DESC)')
        if os.name != 'nt':
            os.chmod(self.path, 0o600)

    def post(self, sender, recipient, subject, body):
        sender = sender.upper()
        recipient = recipient.upper()
        if not CALL_RE.fullmatch(sender) or not (
                recipient == 'ALL' or CALL_RE.fullmatch(recipient)):
            raise ValueError('Invalid BBS callsign')
        if (not 1 <= len(subject) <= 50 or
                not 1 <= len(body) <= MAX_BODY or
                any(c not in '\r\n' and not 32 <= ord(c) <= 126 for c in subject + body)):
            raise ValueError('BBS subject/body must be bounded printable ASCII')
        with self.lock, self.db:
            row = self.db.execute('''INSERT INTO bbs_mail
                 (created_utc,sender,recipient,subject,body)
                 VALUES (?,?,?,?,?)''', (utcnow(),sender,recipient,subject,body))
            self.db.execute('''DELETE FROM bbs_mail WHERE id IN
                 (SELECT id FROM bbs_mail ORDER BY id DESC LIMIT -1 OFFSET ?)''',
                 (self.max_messages,))
            return row.lastrowid

    def list_for(self, call, personal=False, limit=15):
        with self.lock:
            condition = ('recipient=? OR sender=?' if personal else
                         "recipient='ALL' OR recipient=? OR sender=?")
            rows = self.db.execute(
                f'''SELECT id,created_utc,sender,recipient,subject FROM bbs_mail
                    WHERE {condition} ORDER BY id DESC LIMIT ?''',
                (call,call,min(limit,30))).fetchall()
        return [dict(row) for row in rows]

    def read_for(self, number, call):
        if type(number) is not int or number <= 0:
            return None
        with self.lock:
            row = self.db.execute('SELECT * FROM bbs_mail WHERE id=?', (number,)).fetchone()
        if row is None or (row['recipient'] not in ('ALL',call) and row['sender'] != call):
            return None
        return dict(row)

    def admin_list(self, limit=50):
        with self.lock:
            rows = self.db.execute(
                'SELECT * FROM bbs_mail ORDER BY id DESC LIMIT ?', (min(100,max(1,limit)),)
            ).fetchall()
            count = self.db.execute('SELECT COUNT(*) FROM bbs_mail').fetchone()[0]
        return count, [dict(row) for row in rows]

    def admin_delete(self, number):
        if type(number) is not int or number <= 0:
            raise ValueError('Invalid BBS message ID')
        with self.lock, self.db:
            cur=self.db.execute('DELETE FROM bbs_mail WHERE id=?', (number,))
        return bool(cur.rowcount)

    def close(self):
        with self.lock:
            self.db.close()


@dataclass
class Link:
    remote: str
    epoch: int
    last: float
    vr: int = 0
    vs: int = 0
    waiting_ua: bool = True
    output: bytearray = field(default_factory=bytearray)
    input: bytearray = field(default_factory=bytearray)
    unacked: dict | None = None
    remote_busy: bool = False
    stage: str = 'command'
    to: str = ''
    subject: str = ''
    body: list[str] = field(default_factory=list)
    posts: int = 0
    closing: bool = False
    disc_sent: float | None = None


class AX25PBBS:
    """Minimal interoperable AX.25 v2.0 PBBS, no extended SABME/window >1."""

    def __init__(self, path, config, clock=time.monotonic):
        self.clock=clock
        self.config=dict(config)
        self.store=BBSStore(path,self.config['max_messages'])
        self.active=False
        self.session=None
        self.epoch=0
        self.counters=Counter()
        self.tx_times=deque(maxlen=64)
        self.rejected={}
        self.last_error=''

    def configure(self, config):
        self.stop()
        self.config=dict(config)
        self.store.max_messages=config['max_messages']

    def start(self):
        if not self.config['call']:
            raise ValueError('Set a separate BBS callsign before enabling TX')
        self.stop()
        self.active=True

    def stop(self):
        self.active=False
        self.session=None
        self.epoch+=1  # invalidates still queued KISS frames
        self.tx_times.clear()

    def close(self):
        self.stop()
        self.store.close()

    def _build(self, remote, control, payload=b'', response=True):
        # AX.25 command/response C bits in destination/source addresses.
        dst=address_bytes(remote, repeated=not response)
        src=address_bytes(self.config['call'], last=True, repeated=response)
        return encode_kiss_data(dst+src+bytes((control,))+payload)

    def _send(self, send, remote, control, payload=b'', kind='link', response=True):
        now=self.clock()
        while self.tx_times and now-self.tx_times[0]>=60:
            self.tx_times.popleft()
        if len(self.tx_times)>=self.config['max_tx_per_minute']:
            self.counters['rate_limited']+=1
            return False
        cat=f'bbs_{kind}:{self.epoch}'
        if send(self._build(remote,control,payload,response),cat):
            self.tx_times.append(now)
            self.counters['queued_to_kiss']+=1
            return True
        self.counters['queue_full']+=1
        return False

    def _control(self, send, remote, control):
        return self._send(send,remote,control,kind='link')

    def _output(self, text):
        link=self.session
        if link is None:return
        data=(text.replace('\n','\r').encode('ascii','replace')+b'\r')
        remaining=4096-len(link.output)
        if remaining>0:
            link.output.extend(data[:remaining])

    def _welcome(self):
        call=self.config['call']
        self._output(f'\r{self.config["welcome"]} [{call}]')
        self._output('Type H for help, Q to disconnect.')
        self._output(f'Connected: {self.session.remote}')
        self._prompt()

    def _prompt(self):
        self._output('BBS> ')

    @staticmethod
    def _offset(raw):
        at=0
        for _ in range(10):
            if at+7>len(raw):return None
            last=bool(raw[at+6]&1)
            at+=7
            if last:
                return at if at<len(raw) else None
        return None

    def on_frame(self, packet, send):
        """Return True if connected-mode frame addressed to the BBS was handled."""
        if not self.active or packet.simulated or packet.destination!=self.config['call']:
            return False
        if packet.control is None or packet.control==0x03:
            return False
        if packet.path:  # safe subset: direct RF only; no malformed reverse DIGI paths
            self.counters['via_rejected']+=1
            return True
        if not CALL_RE.fullmatch(packet.source):
            return True
        offset=self._offset(packet.raw_ax25)
        if offset is None or packet.raw_ax25[offset]!=packet.control:
            self.counters['invalid']+=1
            return True
        ctrl=packet.control
        now=self.clock()
        source=packet.source
        # U-frames (bit 0+1 both 1); P/F bit can vary.
        if ctrl & 3 == 3:
            base=ctrl & ~0x10
            if base==0x2F:  # SABM, modulo-8
                if self.session is not None and self.session.remote!=source:
                    last=self.rejected.get(source,float('-inf'))
                    if now-last>30:
                        self._control(send,source,0x1F if ctrl&0x10 else 0x0F)
                        self.rejected[source]=now
                    self.counters['busy']+=1
                    return True
                self.epoch+=1
                link=Link(remote=source,epoch=self.epoch,last=now)
                self.session=link
                if not self._control(send,source,0x73 if ctrl&0x10 else 0x63):
                    self.session=None
                    return True
                self.counters['connections']+=1
                self._welcome()
                return True
            if base==0x6F:  # SABME modulo-128 not supported
                self._control(send,source,0x1F if ctrl&0x10 else 0x0F)
                self.counters['sabme_rejected']+=1
                return True
            if self.session is None or self.session.remote!=source:
                return True
            if base==0x43:  # DISC
                self._control(send,source,0x73 if ctrl&0x10 else 0x63)
                self.session=None
                self.epoch+=1
                self.counters['disconnects']+=1
            elif base==0x0F:  # DM
                self.session=None
                self.epoch+=1
            elif base==0x63 and self.session.disc_sent is not None:
                self.session=None
                self.epoch+=1
            return True
        link=self.session
        if link is None or link.remote!=source or link.disc_sent is not None:
            return True
        link.last=now
        if ctrl & 1 == 0:  # I-frame, modulo-8
            at=offset+1
            if at>=len(packet.raw_ax25) or packet.raw_ax25[at]!=0xF0:
                self.counters['pid_rejected']+=1
                return True
            nr=(ctrl>>5)&7
            ns=(ctrl>>1)&7
            self._ack(nr)
            if ns==link.vr:
                link.vr=(link.vr+1)&7
                self._accept_text(packet.raw_ax25[at+1:])
                self.counters['received_i']+=1
                self._control(send,source,0x01 | (link.vr<<5) | (ctrl&0x10))
            elif ns==((link.vr-1)&7):
                self._control(send,source,0x01 | (link.vr<<5) | (ctrl&0x10))
                self.counters['duplicate_i']+=1
            else:
                self._control(send,source,0x09 | (link.vr<<5) | (ctrl&0x10))
                self.counters['out_of_order_i']+=1
            return True
        if ctrl & 3 == 1:  # RR/RNR/REJ supervisory frame
            mode=ctrl&0x0F
            self._ack((ctrl>>5)&7)
            link.remote_busy = mode==0x05
            if mode==0x09 and link.unacked:
                link.unacked['last']=float('-inf')  # REJ requests resend
            if ctrl&0x10:  # respond to poll
                self._control(send,source,(0x05 if link.remote_busy else 0x01)|(link.vr<<5)|0x10)
        return True

    def _ack(self, nr):
        link=self.session
        if link and link.unacked and nr==((link.unacked['ns']+1)&7):
            link.unacked=None
            self.counters['ack_i']+=1

    def _accept_text(self, data):
        link=self.session
        for octet in data[:256]:
            if octet in (10,13):
                if link.input:
                    line=link.input.decode('ascii','replace').strip()
                    link.input.clear()
                    self._command(line)
                continue
            if 32<=octet<=126 and len(link.input)<MAX_LINE:
                link.input.append(octet)
            elif octet not in (9,):
                self.counters['invalid_input']+=1

    def _command(self, line):
        link=self.session
        if not link:return
        if link.stage=='subject':
            if not 1<=len(line)<=50:
                self._output('Subject must be 1-50 printable characters.')
                return
            link.subject=line
            link.stage='body'
            self._output('Enter text, finish with /EX on a separate line.')
            return
        if link.stage=='body':
            if line.upper()=='/EX':
                if not link.body:
                    self._output('Empty message cancelled.')
                else:
                    try:
                        number=self.store.post(link.remote,link.to,link.subject,
                                               '\n'.join(link.body))
                        link.posts+=1
                        self._output(f'Message #{number} stored.')
                    except (sqlite3.Error,ValueError,OSError):
                        self.counters['storage_errors']+=1
                        self._output('Mailbox temporarily unavailable.')
                link.stage='command'
                link.body=[]
                link.to=''
                self._prompt()
                return
            if sum(len(t)+1 for t in link.body)+len(line)>MAX_BODY:
                self._output('Message exceeds 800 characters; finish /EX or Q.')
                return
            link.body.append(line)
            return
        cmd=line.upper()
        if cmd in ('H','?','HELP'):
            self._output('H = help | L = public/relevant mail | LM = my mail')
            self._output('R number = read mail | SP CALL = private | SB = bulletin')
            self._output('Q = disconnect | I = BBS info')
        elif cmd in ('I','INFO'):
            self._output(f'{self.config["call"]} PBBS / AX.25 modulo-8 / direct KISS')
            self._output('Amateur RF is public; callsign is not authenticated.')
        elif cmd in ('L','LIST','LM'):
            personal=cmd=='LM'
            rows=self.store.list_for(link.remote,personal=personal)
            if not rows:self._output('No messages.')
            else:
                for row in rows:
                    self._output(f'#{row["id"]} {row["sender"]}>{row["recipient"]} {row["subject"][:42]}')
        elif cmd.startswith('R ') and cmd[2:].strip().isdigit():
            item=self.store.read_for(int(cmd[2:].strip()),link.remote)
            if item is None:self._output('Message not available.')
            else:
                self._output(f'#{item["id"]} From {item["sender"]} To {item["recipient"]}')
                self._output(f'Subject: {item["subject"]}')
                for entry in item['body'].splitlines()[:15]:
                    self._output(entry[:100])
                if len(item['body'].splitlines())>15:self._output('[truncated]')
        elif cmd=='Q' or cmd=='QUIT':
            self._output('73! Disconnecting.')
            link.closing=True
        elif cmd=='SB' or cmd.startswith('SP '):
            if not self.config['allow_posts']:
                self._output('Posting disabled by sysop.')
            elif link.posts>=3:
                self._output('Session limit: 3 new messages.')
            else:
                target='ALL' if cmd=='SB' else cmd[3:].strip()
                if target!='ALL' and not CALL_RE.fullmatch(target):
                    self._output('Use SP CALLSIGN, e.g. SP OK1ABC-7.')
                else:
                    link.to=target
                    link.stage='subject'
                    self._output(f'Sending to {target}. Enter subject (1-50 chars):')
                    return
        else:
            self._output('Unknown command. Type H.')
        self._prompt()

    def on_tx_written(self, category):
        link=self.session
        if link is None or category.rsplit(':',1)[-1]!=str(link.epoch):
            return
        if category.startswith('bbs_link:') and link.waiting_ua:
            link.waiting_ua=False
        if category.startswith('bbs_data:') and link.unacked:
            link.unacked['queued']=False
            link.unacked['last']=self.clock()

    def on_tx_error(self, category):
        if category.startswith('bbs_'):
            self.counters['tx_errors']+=1
            self.stop()  # fail closed: retry only after explicit admin activation

    def tick(self, send):
        if not self.active or self.session is None:return
        link=self.session
        now=self.clock()
        if now-link.last>=self.config['idle_seconds']:
            self.counters['idle_timeouts']+=1
            self.session=None
            self.epoch+=1
            return
        if link.waiting_ua:return
        if link.disc_sent is not None:
            if now-link.disc_sent>20:
                self.session=None
                self.epoch+=1
            return
        if link.unacked:
            out=link.unacked
            if not out['queued'] and now-out['last']>=T1:
                if out['retries']>=N2:
                    self.counters['retry_timeouts']+=1
                    self.session=None
                    self.epoch+=1
                elif self._send(send,link.remote,out['ctrl'],out['payload'],
                                kind='data',response=False):
                    out['queued']=True
                    out['retries']+=1
            return
        if link.remote_busy:return
        if link.output:
            data=bytes(link.output[:PACLEN])
            ctrl=(link.vs<<1)|(link.vr<<5)
            payload=b'\xF0'+data
            if self._send(send,link.remote,ctrl,payload,kind='data',response=False):
                del link.output[:len(data)]
                link.unacked={'ns':link.vs,'ctrl':ctrl,'payload':payload,
                              'last':now,'queued':True,'retries':0}
                link.vs=(link.vs+1)&7
        elif link.closing:
            if self._control(send,link.remote,0x53):
                link.disc_sent=now

    def snapshot(self):
        count,items=self.store.admin_list(limit=50)
        link=self.session
        return {
            'active':self.active, 'call':self.config['call'],
            'connected':bool(link), 'remote':link.remote if link else '',
            'stage':link.stage if link else '',
            'queued_chars':len(link.output) if link else 0,
            'waiting_ack':bool(link and link.unacked),
            'mail_count':count, 'messages':items, 'stats':dict(self.counters),
            'max_tx_per_minute':self.config['max_tx_per_minute'],
            'allow_posts':self.config['allow_posts'],
            'last_error':self.last_error,
            'capabilities':'AX.25 v2.0 SABM, direct-only, modulo-8 stop-and-wait, ASCII'
        }
