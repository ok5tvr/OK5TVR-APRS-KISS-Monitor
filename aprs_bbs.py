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
        self.db.execute('PRAGMA foreign_keys=ON')
        with self.lock, self.db:
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA synchronous=NORMAL')
            self.db.execute('''CREATE TABLE IF NOT EXISTS bbs_mail (
                id INTEGER PRIMARY KEY,
                created_utc TEXT NOT NULL,
                sender TEXT NOT NULL, recipient TEXT NOT NULL,
                subject TEXT NOT NULL, body TEXT NOT NULL)''')
            self.db.execute('CREATE INDEX IF NOT EXISTS ix_bbs_to ON bbs_mail(recipient,id DESC)')
            # Additive migration: existing mail IDs and contents stay intact.
            self.db.execute('''CREATE TABLE IF NOT EXISTS bbs_reads (
                message_id INTEGER NOT NULL REFERENCES bbs_mail(id) ON DELETE CASCADE,
                callsign TEXT NOT NULL, read_utc TEXT NOT NULL,
                PRIMARY KEY(message_id,callsign))''')
        if os.name != 'nt':
            os.chmod(self.path, 0o600)

    def post(self, sender, recipient, subject, body):
        sender = sender.upper()
        recipient = recipient.upper()
        if not CALL_RE.fullmatch(sender) or not (
                recipient == 'ALL' or CALL_RE.fullmatch(recipient)):
            raise ValueError('Invalid BBS callsign')
        if (not 1 <= len(subject) <= 50 or
                not 1 <= len(body) <= MAX_BODY or not body.strip() or
                any(not 32 <= ord(c) <= 126 for c in subject) or
                any(c not in '\r\n' and not 32 <= ord(c) <= 126 for c in body)):
            raise ValueError('BBS subject/body must be bounded printable ASCII')
        with self.lock, self.db:
            row = self.db.execute('''INSERT INTO bbs_mail
                 (created_utc,sender,recipient,subject,body)
                 VALUES (?,?,?,?,?)''', (utcnow(),sender,recipient,subject,body))
            self.db.execute('''DELETE FROM bbs_mail WHERE id IN
                 (SELECT id FROM bbs_mail ORDER BY id DESC LIMIT -1 OFFSET ?)''',
                 (self.max_messages,))
            ident = row.lastrowid
            self.db.execute('INSERT OR REPLACE INTO bbs_reads VALUES (?,?,?)',
                            (ident, sender, utcnow()))
            return ident

    def list_for(self, call, personal=False, limit=15, offset=0, unread=False):
        call = call.upper()
        with self.lock:
            condition = ('recipient=? OR sender=?' if personal else
                         "recipient='ALL' OR recipient=? OR sender=?")
            read = 'EXISTS(SELECT 1 FROM bbs_reads r WHERE r.message_id=m.id AND r.callsign=?)'
            where = '(' + condition + ')'
            args = [call, call, call]
            if unread:
                where += ' AND NOT ' + read
                args.append(call)
            rows = self.db.execute(
                f'''SELECT id,created_utc,sender,recipient,subject,{read} AS is_read
                    FROM bbs_mail m WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?''',
                (*args, min(30,max(1,limit)), max(0,offset))).fetchall()
        return [dict(row) for row in rows]

    def read_for(self, number, call, mark=True):
        if type(number) is not int or number <= 0:
            return None
        call = call.upper()
        with self.lock, self.db:
            row = self.db.execute('SELECT * FROM bbs_mail WHERE id=?', (number,)).fetchone()
            if row is None or (row['recipient'] not in ('ALL',call) and row['sender'] != call):
                return None
            if mark:
                self.db.execute('INSERT OR REPLACE INTO bbs_reads VALUES (?,?,?)',
                                (number,call,utcnow()))
        return dict(row)

    def delete_for(self, number, call):
        if type(number) is not int or number <= 0:
            return False
        with self.lock, self.db:
            cur = self.db.execute('DELETE FROM bbs_mail WHERE id=? AND (sender=? OR recipient=?)',
                                  (number,call.upper(),call.upper()))
            return bool(cur.rowcount)

    def admin_list(self, limit=50, offset=0):
        with self.lock:
            rows = self.db.execute('''SELECT m.*,
                EXISTS(SELECT 1 FROM bbs_reads r WHERE r.message_id=m.id
                       AND r.callsign=m.recipient) AS recipient_read
                FROM bbs_mail m ORDER BY id DESC LIMIT ? OFFSET ?''',
                (min(100,max(1,limit)),max(0,offset))).fetchall()
            count = self.db.execute('SELECT COUNT(*) FROM bbs_mail').fetchone()[0]
        return count, [dict(row) for row in rows]

    def admin_get(self, number):
        if type(number) is not int or number<=0:
            return None
        with self.lock:
            row=self.db.execute('SELECT * FROM bbs_mail WHERE id=?',(number,)).fetchone()
        return dict(row) if row else None

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
    list_mode: str = 'L'
    list_page: int = 0
    skip_lf: bool = False
    input_overflow: bool = False
    connect_at: float | None = None
    connect_retries: int = 0


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
        self.last_disconnect='not_connected'
        self.client_mode=False
        self.local_call=self.config['call']
        self.console=''

    def configure(self, config):
        self.stop()
        self.config=dict(config)
        self.local_call=self.config['call']
        self.client_mode=False
        self.store.max_messages=config['max_messages']

    def start(self):
        self.client_mode=False
        self.local_call=self.config['call']
        if not self.config['call']:
            raise ValueError('Set a separate BBS callsign before enabling TX')
        self.stop()
        self.active=True

    def stop(self):
        if self.session is not None:
            self.last_disconnect='operator_stop'
        self.active=False
        self.session=None
        self.epoch+=1  # invalidates still queued KISS frames
        self.tx_times.clear()

    def connect(self, remote, local_call, send):
        if not isinstance(remote,str) or not CALL_RE.fullmatch(remote.upper()):
            raise ValueError('Enter a remote BBS callsign with SSID')
        if not CALL_RE.fullmatch(local_call) or remote.upper()==local_call:
            raise ValueError('Local and remote BBS callsigns must differ')
        self.stop()
        self.client_mode=True
        self.local_call=local_call
        self.console=''
        self.active=True
        self.session=Link(remote.upper(),self.epoch,self.clock(),stage='client')
        if not self._send(send,remote.upper(),0x3F,kind='connect',response=False):
            self.stop()
            raise RuntimeError('Cannot queue AX.25 connect request')
        self.last_disconnect=''

    def send_text(self, text):
        if not self.client_mode or not self.active or not self.session or self.session.waiting_ua or self.session.closing:
            raise ValueError('BBS client is not connected')
        if not isinstance(text,str) or not 0<=len(text)<=100 or any(not 32<=ord(c)<=126 for c in text):
            raise ValueError('Send one ASCII line, up to 100 characters')
        if len(self.session.output)>3000:raise ValueError('Wait for the outgoing text queue')
        self._output(text)
        self.console=(self.console+'\n> '+text)[-6000:]

    def close(self):
        self.stop()
        self.store.close()

    def _build(self, remote, control, payload=b'', response=True):
        # AX.25 command/response C bits in destination/source addresses.
        dst=address_bytes(remote, repeated=not response)
        src=address_bytes(self.local_call, last=True, repeated=response)
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
        if not self.active or packet.simulated or packet.destination!=self.local_call:
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
            if base==0x63 and self.client_mode and self.session and self.session.remote==source and self.session.waiting_ua:
                self.session.waiting_ua=False
                self.session.last=now
                self.counters['connections']+=1
                return True
            if base==0x2F and self.client_mode:
                self._control(send,source,0x1F)
                return True
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
                self.last_disconnect=''
                self._welcome()
                return True
            if base==0x6F:  # SABME modulo-128 not supported
                self._control(send,source,0x1F if ctrl&0x10 else 0x0F)
                self.counters['sabme_rejected']+=1
                return True
            if self.session is None or self.session.remote!=source:
                return True
            if base==0x43:  # DISC
                self.last_disconnect='remote_disconnect'
                self._control(send,source,0x73 if ctrl&0x10 else 0x63)
                self.session=None
                self.epoch+=1
                self.counters['disconnects']+=1
            elif base==0x0F:  # DM
                self.last_disconnect='remote_dm'
                self.session=None
                self.epoch+=1
            elif base==0x63 and self.session.disc_sent is not None:
                self.last_disconnect='local_disconnect'
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
        if self.client_mode:
            text=data.decode('ascii','replace').replace('\r\n','\n').replace('\r','\n')
            text=''.join(c for c in text if c in '\n\t' or 32<=ord(c)<=126)
            self.console=(self.console+text)[-6000:]
            return
        link=self.session
        for octet in data[:256]:
            if octet == 10 and link.skip_lf:
                link.skip_lf=False
                continue
            link.skip_lf=octet==13
            if octet in (10,13):
                if link.input_overflow:
                    self._output('Line too long (100 chars); discarded. Retry or /ABORT.')
                elif link.input or link.stage=='body':
                    self._command(link.input.decode('ascii','replace'))
                link.input.clear()
                link.input_overflow=False
                continue
            if octet in (8,127):
                if link.input:link.input.pop()
            elif 32<=octet<=126:
                if len(link.input)<MAX_LINE:link.input.append(octet)
                else:link.input_overflow=True
            elif octet not in (9,):
                self.counters['invalid_input']+=1

    def _begin_message(self, target, subject=''):
        link=self.session
        if not self.config['allow_posts']:
            self._output('Posting disabled by sysop.')
            return False
        if link.posts>=3:
            self._output('Session limit: 3 new messages.')
            return False
        link.to=target
        link.subject=subject
        link.body=[]
        link.stage='body' if subject else 'subject'
        if subject:self._output(f'To {target}, subject: {subject}. Text; /EX saves, /ABORT cancels.')
        else:self._output(f'Sending to {target}. Enter subject (1-50 chars), or /ABORT:')
        return True

    def _command(self, line):
        try:
            self._run_command(line)
        except (sqlite3.Error,OSError):
            self.counters['storage_errors']+=1
            self.last_error='Mailbox storage unavailable'
            self._output('Mailbox temporarily unavailable; retry or /ABORT.')

    def _run_command(self, line):
        link=self.session
        if not link or link.closing:return
        cmd=line.strip().upper()
        if cmd=='/ABORT':
            link.stage='command'
            link.body=[]
            link.to=''
            link.subject=''
            self._output('Draft cancelled.')
            self._prompt()
            return
        if link.stage=='subject':
            line=line.strip()
            if not 1<=len(line)<=50:
                self._output('Subject must be 1-50 printable characters.')
                return
            link.subject=line
            link.stage='body'
            self._output('Enter text; /EX saves, /ABORT cancels on a separate line.')
            return
        if link.stage=='body':
            if cmd=='/EX':
                if not any(part.strip() for part in link.body):
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
            if sum(map(len,link.body))+len(link.body)+len(line)>MAX_BODY:
                self._output('Message exceeds 800 characters; /EX saves, /ABORT cancels.')
                return
            link.body.append(line)
            return
        # Keep each complete response inside the bounded output buffer.
        if len(link.output)>2048:
            self._output('Output busy; wait for the prompt before another command.')
            return
        if cmd in ('H','?','HELP'):
            self._output('H help | I info | Q disconnect')
            self._output('L [page] public/relevant | LM [page] mine | LN [page] unread | N next page')
            self._output('R id read full message | RE id reply | SP CALL personal | SB bulletin')
            self._output('K id YES delete own mail | /ABORT cancel draft | /EX save draft')
            self._output('* = unread; exact callsign/SSID matching; RF calls are not authenticated.')
        elif cmd in ('I','INFO'):
            self._output(f'{self.config["call"]} PBBS / AX.25 modulo-8 / direct KISS')
            self._output('Amateur RF is public; callsign is not authenticated.')
        elif re.fullmatch(r'(L|LIST|LM|LN)( +[0-9]{1,4})?',cmd) or cmd=='N':
            if cmd=='N':
                mode=link.list_mode
                page=link.list_page+1
            else:
                parts=cmd.split()
                mode='L' if parts[0]=='LIST' else parts[0]
                page=max(1,int(parts[1])) if len(parts)>1 else 1
            rows=self.store.list_for(link.remote,personal=mode=='LM',unread=mode=='LN',
                                     limit=16,offset=(page-1)*15)
            link.list_mode,link.list_page=mode,page
            self._output(f'{mode} page {page}')
            if not rows:self._output('No messages.')
            for row in rows[:15]:
                marker=' ' if row['is_read'] else '*'
                self._output(f'{marker}#{row["id"]} {row["sender"]}>{row["recipient"]} {row["subject"][:42]}')
            if len(rows)>15:self._output(f'More: {mode} {page+1} or N')
        elif re.fullmatch(r'R +[0-9]+',cmd):
            item=self.store.read_for(int(cmd.split()[1]),link.remote)
            if item is None:self._output('Message not available.')
            else:
                self._output(f'#{item["id"]} From {item["sender"]} To {item["recipient"]}')
                self._output(f'Subject: {item["subject"]}')
                self._output(item['body'])
        elif re.fullmatch(r'RE +[0-9]+',cmd):
            item=self.store.read_for(int(cmd.split()[1]),link.remote,mark=False)
            if item is None:self._output('Message not available.')
            else:
                target=item['recipient'] if item['sender']==link.remote and item['recipient']!='ALL' else item['sender']
                subject=item['subject'] if item['subject'].upper().startswith('RE:') else 'Re: '+item['subject']
                if self._begin_message(target,subject[:50]):return
        elif re.fullmatch(r'K +[0-9]+(?: +YES)?',cmd):
            parts=cmd.split()
            if len(parts)<3:self._output(f'Confirm deletion: K {parts[1]} YES')
            else:
                removed=self.store.delete_for(int(parts[1]),link.remote)
                self._output('Message deleted.' if removed else 'Message not available or not yours.')
        elif cmd in ('Q','QUIT'):
            self._output('73! Disconnecting.')
            link.closing=True
        elif cmd=='SB' or cmd.startswith('SP '):
            target='ALL' if cmd=='SB' else cmd[3:].strip()
            if target!='ALL' and not CALL_RE.fullmatch(target):
                self._output('Use SP CALLSIGN, e.g. SP OK1ABC-7.')
            elif self._begin_message(target):return
        else:
            self._output('Unknown command. Type H.')
        self._prompt()

    def on_tx_written(self, category):
        link=self.session
        if link is None or category.rsplit(':',1)[-1]!=str(link.epoch):
            return
        if category.startswith('bbs_connect:'):
            link.connect_at=self.clock()
        if category.startswith('bbs_link:') and link.waiting_ua and not self.client_mode:
            link.waiting_ua=False
        if category.startswith('bbs_data:') and link.unacked:
            link.unacked['queued']=False
            link.unacked['last']=self.clock()

    def on_tx_error(self, category):
        if (category.startswith('bbs_') and
                category.rsplit(':',1)[-1]==str(self.epoch)):
            self.counters['tx_errors']+=1
            self.last_error='KISS write failed'
            self.stop()
            self.last_disconnect='tnc_error'

    def tick(self, send):
        if not self.active or self.session is None:return
        link=self.session
        now=self.clock()
        if now-link.last>=self.config['idle_seconds']:
            self.counters['idle_timeouts']+=1
            self.last_disconnect='idle_timeout'
            self.session=None
            self.epoch+=1
            return
        if link.waiting_ua:
            if self.client_mode and link.connect_at is not None and now-link.connect_at>=T1:
                if link.connect_retries>=N2:
                    self.last_disconnect='connect_timeout'
                    self.session=None
                    self.epoch+=1
                elif self._send(send,link.remote,0x3F,kind='connect',response=False):
                    link.connect_retries+=1
                    link.connect_at=None  # retry timer begins at actual KISS write
            return
        if link.disc_sent is not None:
            if now-link.disc_sent>20:
                self.last_disconnect='disconnect_timeout'
                self.session=None
                self.epoch+=1
            return
        if link.unacked:
            out=link.unacked
            if not out['queued'] and now-out['last']>=T1:
                if out['retries']>=N2:
                    self.counters['retry_timeouts']+=1
                    self.last_disconnect='ack_timeout'
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
            if self._send(send,link.remote,0x53,response=False):
                link.disc_sent=now

    def snapshot(self, offset=0, limit=50):
        count,items=self.store.admin_list(limit=limit,offset=offset)
        link=self.session
        return {
            'active':self.active, 'call':self.local_call,
            'role':'client' if self.client_mode else 'server', 'console':self.console,
            'connecting':bool(link and self.client_mode and link.waiting_ua),
            'connected':bool(link and not (self.client_mode and link.waiting_ua)), 'remote':link.remote if link else '',
            'stage':link.stage if link else '',
            'queued_chars':len(link.output) if link else 0,
            'waiting_ack':bool(link and link.unacked),
            'mail_count':count, 'messages':items, 'stats':dict(self.counters),
            'max_tx_per_minute':self.config['max_tx_per_minute'],
            'allow_posts':self.config['allow_posts'],
            'last_error':self.last_error, 'last_disconnect':self.last_disconnect,
            'page_offset':offset, 'page_size':limit,
            'idle_seconds':round(max(0,self.clock()-link.last),1) if link else 0,
            'retries':link.unacked['retries'] if link and link.unacked else 0,
            'remote_busy':bool(link and link.remote_busy),
            'capabilities':'AX.25 v2.0 SABM, direct-only, modulo-8 stop-and-wait, ASCII'
        }
