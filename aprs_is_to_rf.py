"""Selective APRS-IS to RF IGate with third-party AX.25 encapsulation.

Requires explicit runtime operator confirmation. Never automatically forwards an
APRS-IS stream to RF. The transmit callback is owned by the APRS service thread.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import re
import time

from aprs_features import address_bytes, encode_kiss_data

CALL = re.compile(r'^[A-Z0-9]{3,6}(?:-(?:[1-9]|1[0-5]))?$')
OBJECT = re.compile(r'^[A-Z0-9_-]{1,9}$')
SKIP_PATH = {'TCPXX', 'NOGATE', 'RFONLY'}
ALLOWED_TYPES = frozenset(('message', 'position', 'object', 'weather'))
MAX_IS_LINE = 400
MAX_RF_INFO = 230


def server_filter(config):
    """Restrictive APRS-IS 14580 subscriptions; never request full IS feed."""
    parts = []
    if config.get('calls'):
        parts.append('b/' + '/'.join(config['calls']))
    if config.get('objects') and 'object' in config.get('types', []):
        parts.append('o/' + '/'.join(config['objects']))
    return ' '.join(parts)


def validate_filter_config(candidate):
    if not isinstance(candidate, dict):
        raise ValueError('IS->RF config must be an object')
    result = dict(candidate)
    for key, pattern, maximum in (('calls', CALL, 24), ('objects', OBJECT, 16)):
        values = result.get(key)
        if not isinstance(values, list) or len(values) > maximum:
            raise ValueError(f'IS->RF {key}: list limited to {maximum} entries')
        normalized = []
        for value in values:
            if not isinstance(value, str) or not pattern.fullmatch(value.upper()):
                raise ValueError(f'Invalid IS->RF filter: {value!r}')
            if value.upper() not in normalized:
                normalized.append(value.upper())
        result[key] = normalized
    types = result.get('types')
    if not isinstance(types, list) or not types or len(types) > 4:
        raise ValueError('IS->RF: select 1 to 4 packet types')
    if any(type(value) is not str or value not in ALLOWED_TYPES for value in types):
        raise ValueError('IS->RF: unknown packet type')
    result['types'] = sorted(set(types))
    if result.get('rf_path') not in ('', 'WIDE1-1'):
        raise ValueError('IS->RF path: DIRECT or WIDE1-1 only')
    for key, low, high in (
        ('heard_minutes', 5, 120), ('max_per_minute', 1, 6),
        ('max_per_hour', 1, 60), ('min_gap_seconds', 10, 120),
        ('duplicate_seconds', 60, 3600)):
        value = result.get(key)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'IS->RF {key}: expected integer {low}-{high}')
    if result['max_per_hour'] < result['max_per_minute']:
        raise ValueError('IS->RF hourly limit smaller than minute limit')
    if len(server_filter(result)) > 230:
        raise ValueError('Too many stations for APRS-IS server filter')
    return result


@dataclass(frozen=True)
class ISPacket:
    source: str
    destination: str
    path: tuple[str, ...]
    info: str
    kind: str
    target: str = ''
    object_name: str = ''


def parse_tnc2(line: str) -> ISPacket:
    if type(line) is not str or not 1 <= len(line) <= MAX_IS_LINE:
        raise ValueError('invalid APRS-IS line length')
    if any(ord(ch) < 32 or ord(ch) > 126 for ch in line):
        raise ValueError('APRS-IS line contains control or non-ASCII data')
    try:
        header, info = line.split(':', 1)
        source, rest = header.split('>', 1)
    except ValueError as exc:
        raise ValueError('invalid APRS-IS TNC2 header') from exc
    source = source.upper()
    parts = rest.split(',')
    destination = parts[0].upper()
    if not CALL.fullmatch(source) or not CALL.fullmatch(destination):
        raise ValueError('non-AX.25 source or destination')
    if not info or info[0] in ('}', '?') or len(info) > 160:
        raise ValueError('nested third-party, query or oversized payload')
    path = tuple(token.upper() for token in parts[1:])
    if len(path) > 18 or any(not token or len(token) > 20 for token in path):
        raise ValueError('invalid APRS-IS path')
    target, obj_name = '', ''
    if info[0] == ':' and len(info) >= 11 and info[10] == ':':
        kind = 'message'
        target = info[1:10].strip().upper()
    elif info[0] in (';', ')'):
        kind = 'object'
        obj_name = (info[1:10] if info[0] == ';' else re.split(r'[!_]', info[1:], 1)[0]).strip().upper()
    elif info[0] == '_':
        kind = 'weather'
    elif info[0] in ('!', '=', '/', '@', chr(96), "'"):
        kind = 'weather' if info[0] in ('!', '=', '/', '@') and '_' in info[15:28] else 'position'
    else:
        kind = 'other'
    return ISPacket(source, destination, path, info, kind, target, obj_name)


def third_party_kiss(packet: ISPacket, call: str, rf_path: str = '') -> bytes:
    """Wrap using mandatory TCPIP,IGATECALL* inner header; strip original IS path."""
    if not CALL.fullmatch(call):
        raise ValueError('invalid IGate call')
    if rf_path not in ('', 'WIDE1-1'):
        raise ValueError('invalid gated RF path')
    info = f'}}{packet.source}>{packet.destination},TCPIP,{call}*:{packet.info}'
    encoded = info.encode('ascii', 'strict')
    if len(encoded) > MAX_RF_INFO:
        raise ValueError('third-party payload longer than configured RF limit')
    addresses = ['APRS', call] + ([rf_path] if rf_path else [])
    raw = b''.join(address_bytes(value, last=i == len(addresses) - 1)
                   for i, value in enumerate(addresses))
    return encode_kiss_data(raw + b'\x03\xf0' + encoded)


class SelectiveISGate:
    """Single service thread makes all IS->RF TX decisions."""

    def __init__(self, config, igate_call, clock=time.monotonic):
        self.clock = clock
        self.call = igate_call.upper()
        self.config = validate_filter_config(config)
        self.active = False
        self.rf_heard = {}
        self.is_direct = {}
        self.recent_tx = {}
        self.timestamps = deque(maxlen=64)
        self.history = deque(maxlen=60)
        self.counters = Counter()
        self.last_tx = float('-inf')

    def configure(self, config, call):
        self.stop()
        self.config = validate_filter_config(config)
        self.call = call.upper()
        self.recent_tx.clear()
        self.timestamps.clear()

    def start(self):
        if not self.config['calls'] and not (self.config['objects'] and
                                            'object' in self.config['types']):
            raise ValueError('Choose at least one allowed source or object')
        self.active = True

    def stop(self):
        self.active = False

    def note_rf(self, packet):
        if (packet.simulated or packet.control != 0x03 or packet.pid != 0xF0 or
                packet.heard_direct is not True or packet.raw_info.startswith(b'}') or
                not CALL.fullmatch(packet.source.upper())):
            return
        self.rf_heard[packet.source.upper()] = self.clock()
        if len(self.rf_heard) > 1024:
            self._expire()

    def _expire(self):
        now = self.clock()
        self.rf_heard = {call:stamp for call,stamp in self.rf_heard.items() if now-stamp < 7200}
        self.is_direct = {call:stamp for call,stamp in self.is_direct.items() if now-stamp < 7200}
        self.recent_tx = {key:stamp for key,stamp in self.recent_tx.items() if now-stamp < 3600}

    def _remember_is(self, packet):
        if any(x in ('TCPIP*', 'TCPXX*') for x in packet.path):
            self.is_direct[packet.source] = self.clock()
        if len(self.is_direct) > 1024:
            self._expire()

    def _reason(self, packet, now):
        config = self.config
        if packet.source == self.call or self.call in [x.rstrip('*') for x in packet.path]:
            return 'loop_own_igate'
        if any(x.rstrip('*') in SKIP_PATH for x in packet.path):
            return 'blocked_path'
        if packet.kind not in config['types']:
            return 'type_not_selected'
        if packet.kind == 'object':
            if not packet.object_name or packet.object_name not in config['objects']:
                return 'object_not_selected'
        elif packet.source not in config['calls']:
            return 'sender_not_selected'
        if now-self.rf_heard.get(packet.source, float('-inf')) < config['heard_minutes'] * 60:
            return 'sender_already_on_rf'
        if packet.kind == 'message':
            if not CALL.fullmatch(packet.target):
                return 'not_individual_message'
            if now-self.rf_heard.get(packet.target, float('-inf')) >= config['heard_minutes'] * 60:
                return 'recipient_not_heard_direct'
            if now-self.is_direct.get(packet.target, float('-inf')) < config['heard_minutes'] * 60:
                return 'recipient_available_via_internet'
        if len(f'}}{packet.source}>{packet.destination},TCPIP,{self.call}*:{packet.info}') > MAX_RF_INFO:
            return 'rf_frame_too_long'
        return 'matched'

    def inspect(self, line):
        """Dry-run evaluation, never transmits and does not consume rate budget."""
        try:
            packet = parse_tnc2(line)
        except ValueError as exc:
            return {'match':False, 'reason':'invalid_packet', 'detail':str(exc)}
        reason = self._reason(packet, self.clock())
        return {'match':reason == 'matched', 'reason':reason,
                'source':packet.source, 'target':packet.target or packet.object_name,
                'kind':packet.kind}

    def process(self, line, send=None, rf_ready=False, is_ready=False):
        try:
            packet = parse_tnc2(line)
        except ValueError:
            self._record(None, 'invalid_packet')
            return False, 'invalid_packet'
        self._remember_is(packet)
        now = self.clock()
        reason = self._reason(packet, now)
        if reason != 'matched':
            self._record(packet, reason)
            return False, reason
        if not self.active:
            self._record(packet, 'preview_only')
            return False, 'preview_only'
        if not (is_ready and rf_ready and send is not None):
            self._record(packet, 'transport_offline')
            return False, 'transport_offline'
        key = (packet.source, packet.destination, packet.info)
        if now-self.recent_tx.get(key, float('-inf')) < self.config['duplicate_seconds']:
            self._record(packet, 'duplicate')
            return False, 'duplicate'
        if now-self.last_tx < self.config['min_gap_seconds']:
            self._record(packet, 'min_gap')
            return False, 'min_gap'
        if sum(now-t < 60 for t in self.timestamps) >= self.config['max_per_minute']:
            self._record(packet, 'minute_limit')
            return False, 'minute_limit'
        if sum(now-t < 3600 for t in self.timestamps) >= self.config['max_per_hour']:
            self._record(packet, 'hour_limit')
            return False, 'hour_limit'
        try:
            frame = third_party_kiss(packet, self.call, self.config['rf_path'])
        except ValueError:
            self._record(packet, 'invalid_rf_wrapper')
            return False, 'invalid_rf_wrapper'
        if not send(frame):
            self._record(packet, 'tnc_tx_queue_full')
            return False, 'tnc_tx_queue_full'
        self.timestamps.append(now)
        self.recent_tx[key] = now
        if len(self.recent_tx) > 1024:
            self._expire()
        self.last_tx = now
        self._record(packet, 'queued_usb_not_rf_proof')
        return True, 'queued_usb_not_rf_proof'

    def _record(self, packet, reason):
        self.counters[reason] += 1
        self.history.appendleft({
            'at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
            'source':packet.source if packet else '',
            'target':(packet.target or packet.object_name) if packet else '',
            'type':packet.kind if packet else '',
            'reason':reason,
            'tx_queued':reason == 'queued_usb_not_rf_proof',
        })

    def snapshot(self):
        now = self.clock()
        self._expire()
        return {'active':self.active, 'filter':server_filter(self.config),
                'sent_this_minute':sum(now-t < 60 for t in self.timestamps),
                'sent_this_hour':sum(now-t < 3600 for t in self.timestamps),
                'rf_heard_direct_recent':sorted([
                    call for call,stamp in self.rf_heard.items()
                    if now-stamp < self.config['heard_minutes']*60])[:100],
                'counters':dict(self.counters), 'recent':list(self.history),
                'limits':{'per_minute':self.config['max_per_minute'],
                          'per_hour':self.config['max_per_hour'],
                          'min_gap_seconds':self.config['min_gap_seconds']}}
