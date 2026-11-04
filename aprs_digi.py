"""Conservative APRS RF digipeater: traceable New-N, no Internet->RF.

Rules: AX.25 UI 0x03/F0 and TNC-verified FCS, first unused path hop,
no preemption, fill-in WIDE1-1 by default, optional WIDE2-N / TRACE2-N,
never repeat our own callsign/source, block APRS-IS-originated third-party,
30s duplicate suppression, bounded queue and TX airtime rate limiting.

The radio's KISS TNC firmware handles PTT, channel-busy and half duplex;
this module cannot guarantee RF channel is actually free or was transmitted.
"""
from __future__ import annotations

import collections
import hashlib
import re
import time
from dataclasses import dataclass
from typing import Optional

from aprs_features import address_bytes, CALL_RE

MAX_DIGIS = 8
MAX_AX25 = 330
BLOCK_RF_INTERNET = {"TCPIP", "TCPXX"}
ALIAS = re.compile(r"^(WIDE|TRACE)([1-7])$")


@dataclass(frozen=True)
class DigiConfig:
    call: str
    mode: str = "fill"       # fill / regional
    trace: bool = False
    delay_s: float = 4.0     # wait to hear another digi (fill-in viscous)
    max_per_min: int = 6
    min_gap_s: float = 3.0
    duplicate_s: float = 30.0

    def validate(self):
        if not CALL_RE.fullmatch(self.call.upper()) or self.call.upper().startswith("WIDE"):
            raise ValueError("Vyplň platnou vlastní volací značku včetně SSID pro DIGI.")
        if self.mode not in ("fill", "regional"):
            raise ValueError("Neznámý režim DIGI.")
        if not 0 <= self.delay_s <= 10:
            raise ValueError("Zpoždění musí být 0–10 sekund.")
        if not 1 <= self.max_per_min <= 12:
            raise ValueError("Maximálně 1–12 paketů za minutu.")
        if not 1 <= self.min_gap_s <= 30:
            raise ValueError("Minimální odstup TX musí být 1–30 sekund.")
        if not 15 <= self.duplicate_s <= 120:
            raise ValueError("Paměť duplicit musí být 15–120 sekund.")


@dataclass(frozen=True)
class Address:
    call: str
    ssid: int
    used: bool
    raw: bytes

    @property
    def text(self):
        return self.call + (f"-{self.ssid}" if self.ssid else "")


def _addr(chunk: bytes) -> Address:
    if len(chunk) != 7:
        raise ValueError("Neúplná AX.25 adresa")
    # Reject high bit in callsign character bytes and invalid shifted letters.
    if any(x & 1 for x in chunk[:6]):
        raise ValueError("Neplatné bajty adresy AX.25")
    value = ''.join(chr(x >> 1) for x in chunk[:6]).rstrip(' ')
    if not re.fullmatch(r"[A-Z0-9]{1,6}", value):
        raise ValueError("Neplatná AX.25 adresa")
    return Address(value, (chunk[6] >> 1) & 0x0F, bool(chunk[6] & 0x80), chunk)


@dataclass(frozen=True)
class RFFrame:
    addresses: tuple[Address, ...]
    info: bytes
    raw: bytes

    @property
    def signature(self) -> bytes:
        # Ignore the path/H-bits; duplicates relayed through several digi routes
        # are the same packet, provided that source, destination, and info match.
        src, dst = self.addresses[1].text, self.addresses[0].text
        return hashlib.blake2s(src.encode() + b'>' + dst.encode() + b':' + self.info,
                               digest_size=16).digest()

    @property
    def path(self) -> str:
        return ','.join(a.text + ('*' if a.used else '') for a in self.addresses[2:])


def read_ui_frame(raw: bytes) -> RFFrame:
    if not 16 <= len(raw) <= MAX_AX25:
        raise ValueError("Rámec mimo povolenou délku")
    addresses = []
    offset = 0
    for _ in range(2 + MAX_DIGIS):
        if len(raw) < offset + 7:
            raise ValueError("Neúplná AX.25 cesta")
        address = _addr(raw[offset:offset+7])
        addresses.append(address)
        offset += 7
        if raw[offset-1] & 1:
            break
    else:
        raise ValueError("AX.25 povoluje max. 8 DIGI adres")
    if len(addresses) < 2 or offset + 2 > len(raw):
        raise ValueError("Chybí zdroj nebo PID")
    if raw[offset:offset+2] != b'\x03\xf0':
        raise ValueError("Jen AX.25 UI, PID F0")
    if not raw[offset+2:]:
        raise ValueError("Prázdný APRS obsah")
    return RFFrame(tuple(addresses), raw[offset+2:], raw)


def _encode_modified(addresses: list[Address], info: bytes) -> bytes:
    if not 2 <= len(addresses) <= 2 + MAX_DIGIS:
        raise ValueError("Příliš mnoho DIGI adres")
    out = bytearray()
    for ix, addr in enumerate(addresses):
        # Preserve the original shifted address and reserved/C bits;
        # change H-bit only for digipeaters. E-bit is set only on last.
        if addr.raw:
            chunk = bytearray(addr.raw)
        else:
            chunk = bytearray(address_bytes(addr.text))
        chunk[6] &= 0xFE
        if ix >= 2:
            if addr.used: chunk[6] |= 0x80
            else: chunk[6] &= 0x7F
        if ix == len(addresses)-1: chunk[6] |= 1
        out.extend(chunk)
    out.extend(b'\x03\xF0')
    out.extend(info)
    if len(out) > MAX_AX25:
        raise ValueError("Příliš dlouhý výstupní rámec")
    return bytes(out)


def _self_address(call: str, used=True) -> Address:
    raw = address_bytes(call, repeated=used)
    return _addr(raw)


def rewrite_digi(raw: bytes, config: DigiConfig) -> tuple[Optional[bytes], str]:
    """Return a rewritten RF frame or a reason for not repeating it."""
    try:
        config.validate()
        frame = read_ui_frame(raw)
    except ValueError as exc:
        return None, str(exc)
    own = config.call.upper()
    if frame.addresses[1].text == own:
        return None, "Vlastní zdrojová značka"
    path = list(frame.addresses[2:])
    if not path:
        return None, "DIRECT bez DIGI cesty"
    if any(p.used and p.text == own for p in path):
        return None, "Vlastní značka již opakovala paket"
    if any(p.call in BLOCK_RF_INTERNET or p.call.startswith('QA') for p in path):
        return None, "Paket označený jako Internet / nepovolená RF cesta"
    if frame.info[:1] in (b'?', b'}'):
        return None, "Obecný dotaz nebo 3rd-party (bez automatického RF opakování)"
    # No pre-emptive digipeating; used addresses must form a contiguous prefix.
    unused_seen = False
    for p in path:
        if not p.used: unused_seen = True
        elif unused_seen:
            return None, "Nekonzistentní H-bity cesty"
    current = next((ix for ix, p in enumerate(path) if not p.used), None)
    if current is None:
        return None, "Všechny přeskoky byly využity"
    hop = path[current]
    if any(p.text == own for ix,p in enumerate(path) if ix != current):
        return None, "Vlastní značka se v cestě opakuje"
    if hop.text == own:
        path[current] = _self_address(own)
    elif hop.call == 'WIDE1' and hop.ssid == 1 and current == 0:
        path[current] = _self_address(own)
    elif config.mode == 'regional':
        match = ALIAS.fullmatch(hop.call)
        if not match:
            return None, "První nevyužitý hop není podporován"
        family, requested = match.group(1), int(match.group(2))
        if (requested != 2 or not 1 <= hop.ssid <= requested
                or (family == 'TRACE' and not config.trace)):
            return None, "Cesta mimo regionální limit WIDE2-N / TRACE2-N"
        if hop.ssid == 1:
            path[current] = _self_address(own)
        else:
            if len(path) >= MAX_DIGIS:
                return None, "Nelze přidat trasovací značku: plných 8 DIGI adres"
            remaining = _self_address(f"{hop.call}-{hop.ssid-1}", used=False)
            path[current:current+1] = [_self_address(own), remaining]
    else:
        return None, "Fill-in opakuje pouze WIDE1-1 nebo vlastní značku"
    try:
        return _encode_modified([frame.addresses[0], frame.addresses[1]] + path, frame.info), 'OK'
    except ValueError as exc:
        return None, str(exc)


@dataclass
class Pending:
    signature: bytes
    raw: bytes
    input_path: str
    due: float
    created: float


class DigiRepeater:
    """Explicitly enabled DIGI scheduler; never writes to serial port by itself."""
    def __init__(self, config: DigiConfig):
        config.validate()
        self.config = config
        self.enabled = False
        self.pending: dict[bytes, Pending] = {}
        self.sent_cache: dict[bytes, float] = {}
        self.tx_times: collections.deque[float] = collections.deque()
        self.last_tx_at = float('-inf')
        self.stats = collections.Counter()
        self.last_action = "Vypnuto"

    def start(self):
        self.pending.clear()
        self.enabled = True
        self.last_action = "Zapnuto (čekám na RF)"

    def stop(self):
        self.enabled = False
        self.pending.clear()
        self.last_action = "Vypnuto"

    def _tidy(self, now):
        self.sent_cache = {key:stamp for key,stamp in self.sent_cache.items()
                           if now-stamp < self.config.duplicate_s}
        while self.tx_times and now-self.tx_times[0] >= 60.0:
            self.tx_times.popleft()
        for key, p in list(self.pending.items()):
            if now-p.created > 16:
                del self.pending[key]
                self.stats['expired'] += 1

    def receive(self, raw: bytes, now: float | None = None) -> str:
        if not self.enabled:
            return "Vypnuto"
        now = time.monotonic() if now is None else now
        self._tidy(now)
        self.stats['received'] += 1
        try:
            frame = read_ui_frame(raw)
        except ValueError as exc:
            self.stats['rejected'] += 1
            return str(exc)
        sig = frame.signature
        if sig in self.sent_cache:
            self.stats['duplicates'] += 1
            return "Duplicitní paket: již retransmitován"
        if sig in self.pending:
            # A copy that has already been repeated elsewhere suppresses a
            # waiting viscous fill-in transmission.
            if any(p.used for p in frame.addresses[2:]):
                del self.pending[sig]
                self.stats['suppressed'] += 1
                return "Viscous: zachycen přenos jiného DIGI, vlastní zrušen"
            self.stats['duplicates'] += 1
            return "Paket již čeká na opakování"
        rewritten, reason = rewrite_digi(raw, self.config)
        if rewritten is None:
            self.stats['rejected'] += 1
            return reason
        if len(self.pending) >= 12:
            self.stats['rejected'] += 1
            return "Fronta DIGI je plná"
        is_first_hop = not any(p.used for p in frame.addresses[2:])
        wait = self.config.delay_s if is_first_hop else min(1.0, self.config.delay_s)
        self.pending[sig] = Pending(sig, rewritten, frame.path, now+wait, now)
        self.stats['scheduled'] += 1
        self.last_action = "Čeká na opakování: " + frame.addresses[1].text
        return "Plánováno za %.1f s" % wait

    def ready(self, now: float | None = None) -> Pending | None:
        if not self.enabled:
            return None
        now = time.monotonic() if now is None else now
        self._tidy(now)
        if not self.pending:
            return None
        if now - self.last_tx_at < self.config.min_gap_s:
            return None
        due = min(self.pending.values(), key=lambda p:p.due)
        if due.due > now:
            return None
        if len(self.tx_times) >= self.config.max_per_min:
            del self.pending[due.signature]
            self.stats['rate_limited'] += 1
            self.last_action = "Omezení: maximální počet TX za minutu"
            return None
        return due

    def mark_queued(self, signature: bytes, now: float | None = None):
        now = time.monotonic() if now is None else now
        item = self.pending.pop(signature, None)
        if item is None:
            return
        self.sent_cache[signature] = now
        self.tx_times.append(now)
        self.last_tx_at = now
        self.stats['tx_queued'] += 1
        self.last_action = 'KISS TX fronta: ' + item.input_path

    def mark_written(self):
        self.stats['tx_written'] += 1
        self.last_action = "Paket předán USB KISS TNC"

    def mark_error(self):
        self.stats['tx_errors'] += 1
        self.last_action = "Chyba USB přenosu DIGI"

    def snapshot(self) -> dict:
        return {"enabled": self.enabled, "call": self.config.call,
                "mode": self.config.mode, "trace": self.config.trace,
                "pending": len(self.pending), "last_action": self.last_action,
                **{k:int(self.stats.get(k,0)) for k in ('received','scheduled','duplicates','suppressed','rejected',
                       'rate_limited','expired','tx_queued','tx_written','tx_errors')}}
