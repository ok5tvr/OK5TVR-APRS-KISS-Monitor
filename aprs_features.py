"""APRS packet handling, RF->IS gateway, receive-only APRS-IS feed and state.

IS->RF policy lives in aprs_is_to_rf.py and is disabled until activated.
"""
from __future__ import annotations

import collections
import queue
import re
import socket
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from aprs_geo import distance_bearing

FEND, FESC, TFEND, TFESC = 0xC0, 0xDB, 0xDC, 0xDD
BLOCKED = {"TCPIP", "TCPXX", "NOGATE", "RFONLY"}
CALL_RE = re.compile(r"^[A-Z0-9]{3,6}(?:-(?:[1-9]|1[0-5]))?$")
IS_CALL_RE = re.compile(r"^[A-Z0-9]{3,9}(?:-[A-Z0-9]{1,2})?$")


def address_bytes(text: str, last: bool = False, repeated: bool = False) -> bytes:
    """Encode a single AX.25 address; only SSIDs 0-15 are valid on RF."""
    text = text.upper().strip()
    if not CALL_RE.fullmatch(text):
        raise ValueError(f"Neplatná AX.25 značka: {text!r}. Použij např. OK5TVR-9.")
    name, _, ssid = text.partition("-")
    ssid_int = int(ssid) if ssid else 0
    return (bytes(ord(c) << 1 for c in name.ljust(6))
            + bytes([0x60 | (ssid_int << 1) | (0x80 if repeated else 0) | int(last)]))


def encode_ui_packet(source: str, destination: str, path: str, payload: str) -> bytes:
    """Encode AX.25 UI PID F0 payload, without FCS (KISS TNC handles it)."""
    hops = [p.strip().upper() for p in path.split(",") if p.strip()]
    if len(hops) > 3:
        raise ValueError("Pro test povoleny maximálně 3 digipeatery v cestě.")
    info = payload.encode("ascii", errors="strict")
    if not info or len(info) > 100 or any(c < 32 or c > 126 for c in info):
        raise ValueError("Obsah musí mít 1–100 tisknutelných ASCII znaků.")
    if not info.startswith((b">", b"!", b"=", b"@", b"/", b":", b";", b"T#")):
        raise ValueError("Obsah musí začínat typem APRS (například > pro status).")
    addresses = [destination, source] + hops
    result = b"".join(address_bytes(s, last=i == len(addresses)-1)
                      for i, s in enumerate(addresses))
    return result + b"\x03\xF0" + info


def encode_kiss_data(ax25: bytes, port: int = 0) -> bytes:
    if not 0 <= port <= 15 or not ax25:
        raise ValueError("Neplatný KISS port nebo prázdný rámec")
    blob = bytes([port << 4]) + ax25
    blob = blob.replace(b"\xDB", b"\xDB\xDD").replace(b"\xC0", b"\xDB\xDC")
    return b"\xC0" + blob + b"\xC0"


def _base91(value: bytes) -> int | None:
    if len(value) != 4 or any(not 33 <= b <= 123 for b in value):
        return None
    result = 0
    for c in value:
        result = result * 91 + (c - 33)
    return result


def _nmea_coordinate(raw: str, hemisphere: str, latitude: bool) -> float | None:
    """NMEA DDMM.mmmm or DDDMM.mmmm, with a valid hemisphere and degrees."""
    deg_digits=2 if latitude else 3
    hemi_valid='NS' if latitude else 'EW'
    if (hemisphere not in hemi_valid or not raw or
            not re.fullmatch(r'\d{'+str(deg_digits+2)+r',}\.\d+', raw)):
        return None
    integer, fract = raw.split('.',1)
    if len(integer) != deg_digits + 2:
        return None
    degrees, minutes=int(integer[:deg_digits]),float(integer[deg_digits:]+'.'+fract)
    limit=90 if latitude else 180
    if degrees>limit or not 0<=minutes<60 or (degrees==limit and minutes!=0):
        return None
    value=degrees+minutes/60
    return -value if hemisphere in 'SW' else value


def _nmea_position(info: bytes) -> dict[str, Any] | None:
    """APRS $GPRMC/$GNRMC, $GPGGA and $GPGLL GPS positions.

    A present NMEA checksum must be correct. No fix -> no map marker.
    """
    if not info.startswith(b'$') or len(info)>200:
        return None
    try:
        text=info.decode('ascii').strip()
    except UnicodeDecodeError:
        return None
    if not text.startswith('$'):
        return None
    if '*' in text:
        body,cs=text[1:].split('*',1)
        if not re.fullmatch(r'[0-9A-Fa-f]{2}',cs):
            return None
        calculated=0
        for ch in body:calculated ^= ord(ch)
        if calculated!=int(cs,16):return None
    else:body=text[1:]
    fields=body.split(',')
    if not fields or not re.fullmatch(r'[A-Z]{2}(?:RMC|GGA|GLL)',fields[0]):return None
    typ=fields[0][-3:]
    try:
        if typ=='RMC':
            if len(fields)<7 or fields[2]!='A':return None
            lat_raw,ns,lon_raw,ew=fields[3:7]
        elif typ=='GGA':
            if len(fields)<7 or not fields[6].isdigit() or int(fields[6])<=0:return None
            lat_raw,ns,lon_raw,ew=fields[2:6]
        else:
            if len(fields)<7 or fields[6]!='A':return None
            lat_raw,ns,lon_raw,ew=fields[1:5]
    except (ValueError,IndexError):return None
    lat=_nmea_coordinate(lat_raw,ns,True)
    lon=_nmea_coordinate(lon_raw,ew,False)
    if lat is None or lon is None:return None
    return dict(lat=round(lat,6),lon=round(lon,6),format='NMEA '+typ,
                label=None,kind='stanice')


def _third_party_position(info: bytes) -> dict[str, Any] | None:
    """Position encapsulated as }SRC>DST,PATH:payload (not DIRECT RF)."""
    if not info.startswith(b'}') or len(info)>512:
        return None
    try:
        header,inner=info[1:].split(b':',1)
        origin,remainder=header.split(b'>',1)
        source=origin.decode('ascii').upper()
        dest=remainder.split(b',',1)[0].decode('ascii').upper()
    except (ValueError,UnicodeDecodeError):
        return None
    if not CALL_RE.fullmatch(source) or not re.fullmatch(r'[A-Z0-9]{1,6}(?:-\d{1,2})?',dest):
        return None
    if inner.startswith(b'}'):return None
    position=parse_position(inner,dest)
    if position:
        position['source']=source
        position['third_party']=True
        position['format']='3rd-party '+position['format']
    return position


def _symbol_from_bytes(table: int, glyph: int) -> str | None:
    """APRS table/code pair; overlays use the table byte in place of backslash."""
    valid_table = table in (ord('/'), ord('\\')) or (
        ord('0') <= table <= ord('9') or ord('A') <= table <= ord('Z')
        or ord('a') <= table <= ord('z'))
    return chr(table) + chr(glyph) if valid_table and 33 <= glyph <= 126 else None


def parse_position(info: bytes, destination: str = "") -> dict[str, Any] | None:
    """Position-bearing APRS types: normal, compressed, Mic-E, objects,
    items, NMEA GPS sentences and third-party nested positions.

    No coordinates are fabricated for status/messages/telemetry or ambiguous
    and malformed positions.
    """
    if not info:
        return None
    if info.startswith(b'$'):
        return _nmea_position(info)
    if info.startswith(b'}'):
        return _third_party_position(info)
    data = info
    kind = "stanice"
    label = None
    if info[:1] == b";" and len(info) >= 19 and info[10:11] in (b"*", b"_"):
        # ;OBJECTNAM*DDHHMMzDDMM.hhN/DDDMM.hhE...
        label = info[1:10].decode("ascii", "replace").strip()
        data = b"!" + info[18:]
        kind = "objekt"
    elif info[:1] == b")":
        # )ITEM!DDMM.hhN/DDDMM.hhE...
        sep = next((i for i in range(1, min(len(info), 11)) if info[i] in (ord("!"), ord("_"))), None)
        if sep is not None:
            label = info[1:sep].decode("ascii", "replace").strip()
            data = b"!" + info[sep+1:]
            kind = "položka"

    if data[:1] in (b"!", b"=", b"/", b"@"):
        p = data[8:] if data[:1] in (b"/", b"@") else data[1:]
        if len(p) >= 19:
            lat_match = re.fullmatch(rb"(\d{2})(\d{2}\.\d{2})([NS])", p[:8])
            lon_match = re.fullmatch(rb"(\d{3})(\d{2}\.\d{2})([EW])", p[9:18])
            if lat_match and lon_match:
                la_deg = int(lat_match[1]); la_min = float(lat_match[2]); lo_deg = int(lon_match[1]); lo_min = float(lon_match[2])
                if (la_deg <= 90 and lo_deg <= 180 and la_min < 60 and lo_min < 60
                        and (la_deg < 90 or la_min == 0) and (lo_deg < 180 or lo_min == 0)):
                    lat = (la_deg + la_min / 60) * (-1 if lat_match[3] == b"S" else 1)
                    lon = (lo_deg + lo_min / 60) * (-1 if lon_match[3] == b"W" else 1)
                    return dict(lat=round(lat, 6), lon=round(lon, 6), format="nekomprimovaná", label=label, kind=kind, symbol=_symbol_from_bytes(p[8], p[18]))
        # An uncompressed report starts with digits; never reinterpret an invalid
        # DDMM.mmN report as compressed coordinates (would put bogus pins on map).
        if len(p) >= 10 and (p[0] in b"/\\" or p[0] in b"ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
            a, b = _base91(p[1:5]), _base91(p[5:9])
            if a is not None and b is not None and 33 <= p[9] <= 126:
                lat, lon = 90 - a / 380926.0, -180 + b / 190463.0
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return dict(lat=round(lat, 6), lon=round(lon, 6), format="komprimovaná", label=label, kind=kind, symbol=_symbol_from_bytes(p[0], p[9]))

    if info[:1] in (b"'", b"`") and len(info) >= 9:
        dest = destination.split("-", 1)[0].upper().ljust(6)
        if len(dest) == 6:
            digits = []
            for ch in dest:
                if "0" <= ch <= "9": digits.append(ord(ch)-48)
                elif "A" <= ch <= "J": digits.append(ord(ch)-65)
                elif "P" <= ch <= "Y": digits.append(ord(ch)-80)
                else: digits = []; break  # Special position ambiguity: no guess
            if len(digits) == 6:
                lat_deg = digits[0]*10 + digits[1]
                lat_mins = digits[2]*10 + digits[3] + (digits[4]*10 + digits[5])/100
                lon_deg = info[1] - 28 + (100 if "P" <= dest[4] <= "Y" else 0)
                if 180 <= lon_deg <= 189: lon_deg -= 80
                elif 190 <= lon_deg <= 199: lon_deg -= 190
                lon_min = info[2] - 28
                if lon_min >= 60: lon_min -= 60
                lon_hund = info[3] - 28
                if (lat_deg <= 90 and 0 <= lat_mins < 60 and 0 <= lon_deg <= 180
                        and 0 <= lon_min < 60 and 0 <= lon_hund <= 99):
                    lat = (lat_deg + lat_mins/60) * (1 if "P" <= dest[3] <= "Y" else -1)
                    lon = (lon_deg + (lon_min + lon_hund/100)/60) * (-1 if "P" <= dest[5] <= "Y" else 1)
                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                        return dict(lat=round(lat, 6), lon=round(lon, 6), format="Mic-E", label=label, kind=kind, symbol=_symbol_from_bytes(info[8], info[7]))
    return None


def _forbidden_path(path: list[str]) -> bool:
    for p in path:
        node = p.rstrip("*").upper()
        if node in BLOCKED or node.startswith("QA") or node == "I":
            return True
    return False


def _parse_tnc2(text: str):
    """For 3rd-party encapsulated packets only; preserve payload exactly."""
    try:
        header, data = text.split(":", 1)
        src, dest_and_hops = header.split(">", 1)
        chunks = dest_and_hops.split(",")
        if not (CALL_RE.fullmatch(src.upper()) and chunks and chunks[0].strip()):
            return None
        return src, chunks[0], chunks[1:], data
    except ValueError:
        return None


def igate_tnc2(packet, igate_call: str) -> tuple[str | None, str]:
    """Build RFC-aligned receive-only IGate line, or explain why not.

    KISS frames are FCS-verified by the UV-K1 TNC. qAO denotes no IS->RF messaging.
    """
    if getattr(packet, "simulated", False):
        return None, "DEMO rámec"
    if getattr(packet, "control", None) != 0x03 or getattr(packet, "pid", None) != 0xF0:
        return None, "Nejde o AX.25 UI PID F0"
    source, dest = packet.source, packet.destination
    if not CALL_RE.fullmatch(source.upper()):
        return None, "Neplatná zdrojová značka"
    if not re.fullmatch(r"[A-Z0-9]{1,6}(?:-(?:[1-9]|1[0-5]))?", dest.upper()):
        return None, "Neplatný cíl"
    path = packet.path.split(",") if packet.path else []
    if _forbidden_path(path):
        return None, "NOGATE/RFONLY/TCPIP/TCPXX nebo nepovolená cesta"
    info = getattr(packet, "raw_info", b"")
    if not info or info.startswith(b"?"):
        return None, "Obecný dotaz nebo prázdný rámec"
    if b"\r" in info or b"\n" in info or b"\x00" in info:
        return None, "Neplatný řídicí znak v datech"
    # Third party: gate only its inner packet, only when RF-origin, never TCPIP/TCPXX.
    if info.startswith(b"}"):
        parsed = _parse_tnc2(info[1:].decode("latin-1"))
        if not parsed:
            return None, "Neplatný third-party paket"
        source, dest, path, content = parsed
        if _forbidden_path(path) or content.startswith("?") or content.startswith("}"):
            return None, "Third-party / internetový / obecný dotaz"
        if any(c in content for c in ("\r", "\n", "\x00")):
            return None, "Řídicí znak uvnitř third-party"
        info_str = content
    else:
        info_str = info.decode("latin-1")
    if not IS_CALL_RE.fullmatch(igate_call.upper()) or not re.fullmatch(r"[0-9A-Z-]+", igate_call.upper()):
        return None, "Neplatná značka iGate"
    # Preserve RF header and path; add receive-only qAO,IGATECALL.
    line = f"{source}>{dest}" + ("," + ",".join(path) if path else "")
    line += f",qAO,{igate_call.upper()}:{info_str}"
    if len(line.encode("latin-1")) + 2 > 512:
        return None, "Paket překračuje 512 B APRS-IS limit"
    return line, "OK"


class MonitorState:
    def __init__(self):
        self.lock = threading.RLock()
        self.history = collections.deque(maxlen=220)
        self.stations: dict[str, dict] = {}
        self.position_trails: dict[str, collections.deque] = {}  # max 32 recent fixes per station
        self.type_counts = collections.Counter()
        self.rx = self.demo = self.tx_requests = self.igate_sent = self.igate_rejected = 0
        self.igate_status = "Vypnuto"
        self.rf_status = "Odpojeno"
        self.start = datetime.now().astimezone().isoformat(timespec="seconds")
        self.own_position = None
        self.digi_position = None
        self.telemetry = {}
        self.digi = {"enabled":False,"last_action":"Vypnuto","tx_written":0,"pending":0}
        self.beacons_sent = 0

    @staticmethod
    def _new_station(call):
        return dict(call=call,count=0,last='',lat=None,lon=None,kind='',summary='',
                    direct=None,position_direct=None,direct_count=0,via_count=0,
                    receivers=[], 
                    is_object=False,source_call=None,position_format=None,symbol=None)

    def add(self, packet):
        with self.lock:
            if packet.simulated: self.demo += 1
            else: self.rx += 1
            self.type_counts[packet.kind] += 1
            self.history.appendleft(dict(time=packet.timestamp, source=packet.source,
                                         destination=packet.destination,path=packet.path,
                                         kind=packet.kind,summary=packet.summary,
                                         direct=packet.heard_direct,
                                         demo=bool(packet.simulated),gate=getattr(packet,'gate',''),
                                         receiver=getattr(packet,'receiver','primary'),
                                         payload=getattr(packet,'payload','')[:260],
                                         hex_data=getattr(packet,'hex_data','')[:1200]))
            if packet.source == '?' or packet.simulated:
                return
            entry=self.stations.setdefault(packet.source,self._new_station(packet.source))
            entry['count']+=1;entry['last']=packet.timestamp
            receiver=getattr(packet,'receiver','primary')
            if receiver not in entry['receivers']:
                entry['receivers'].append(receiver)
                entry['receivers']=entry['receivers'][-3:]
            entry['kind']=packet.kind;entry['summary']=packet.summary[:180]
            if packet.heard_direct is not None:
                entry['direct']=packet.heard_direct
                entry['direct_count' if packet.heard_direct else 'via_count']+=1
            if packet.latitude is not None and packet.longitude is not None:
                # A Mic-E or compressed location belongs to the originating
                # station. Objects are separate points and cannot be treated
                # as stations directly heard over the air.
                source=packet.position_source or packet.source
                key=packet.position_label or source
                target=self.stations.setdefault(key,self._new_station(key))
                if key!=packet.source:
                    target['count']+=1
                object_point=bool(packet.position_label)
                third_party=bool(packet.position_source)
                position_direct=packet.heard_direct if not(object_point or third_party) else None
                target.update(last=packet.timestamp,lat=packet.latitude,lon=packet.longitude,
                              kind=('Objekt' if object_point else packet.kind),
                              summary=packet.summary[:180],position_direct=position_direct,
                              is_object=object_point,source_call=packet.source,
                              position_format=packet.position_format)
                # Bound the position history: 32 fixes per station, only changed
                # GPS positions. Tracking never includes simulated frames.
                if not object_point and not third_party:
                    trail = self.position_trails.setdefault(key, collections.deque(maxlen=32))
                    lat, lon = target['lat'], target['lon']
                    if not trail or (trail[-1]['lat'], trail[-1]['lon']) != (lat, lon):
                        trail.append({'lat': lat, 'lon': lon, 'time': packet.timestamp,
                                      'direct': position_direct})
                if packet.symbol:
                    target['symbol'] = packet.symbol
                if third_party:
                    target['direct']=False  # A nested origin was not heard directly.
            if len(self.stations)>1000:
                drop=min(self.stations,key=lambda k:self.stations[k]['last'])
                del self.stations[drop]
                self.position_trails.pop(drop, None)

    def set_own_position(self, position):
        with self.lock:
            self.own_position = dict(position) if position else None

    def set_digi_position(self, position):
        with self.lock:
            self.digi_position = dict(position) if position else None

    def set_telemetry(self, metrics):
        with self.lock:
            self.telemetry = dict(metrics)

    def update_digi(self, digi):
        with self.lock:
            self.digi = dict(digi)

    def note_beacon(self):
        with self.lock:
            self.beacons_sent += 1

    def note_tx(self):
        with self.lock: self.tx_requests += 1

    def note_igate(self, sent: bool):
        with self.lock:
            if sent: self.igate_sent += 1
            else: self.igate_rejected += 1

    def update_status(self, igate=None, radio=None):
        with self.lock:
            if igate is not None: self.igate_status = igate
            if radio is not None: self.rf_status = radio

    def _station_snapshot(self):
        """Compute km and initial bearing from configurable iGate/DIGI QTH.

        Our position is the shared QTH of the iGate and DIGI. Return None when
        unset; never use a hardcoded map-centre as a geographic origin.
        """
        origin=self.own_position or self.digi_position
        result=[]
        for station in self.stations.values():
            station=dict(station)
            station.update(distance_km=None,bearing_deg=None,compass_cs='',compass_en='')
            if (origin and origin.get('lat') is not None and origin.get('lon') is not None
                    and station.get('lat') is not None and station.get('lon') is not None):
                try:
                    station.update(distance_bearing(origin['lat'],origin['lon'],station['lat'],station['lon']))
                except (TypeError,ValueError):pass
            station['trail'] = list(self.position_trails.get(station['call'], ()))
            result.append(station)
        return result

    def snapshot(self):
        with self.lock:
            return {"version":"2.3.0-dev", "start":self.start, "time":datetime.now().astimezone().isoformat(timespec="seconds"),
                    "rf_status":self.rf_status, "igate_status":self.igate_status, "rx":self.rx, "demo":self.demo,
                    "tx_requests":self.tx_requests, "igate_sent":self.igate_sent,"igate_rejected":self.igate_rejected,
                    "beacons_sent":self.beacons_sent, "own_position":self.own_position,
                    "digi_position":self.digi_position, "telemetry":dict(self.telemetry),
                    "digi":dict(self.digi),
                    "station_count":len(self.stations), "position_count":sum(1 for x in self.stations.values() if x["lat"] is not None),
                    "types":dict(self.type_counts), "stations":self._station_snapshot(),"history":list(self.history),
                    "direct_count":sum(1 for x in self.stations.values() if x['direct'] is True),
                    "via_count":sum(1 for x in self.stations.values() if x['direct'] is False)}


class APRSISClient(threading.Thread):
    """Verified APRS-IS connection; receive/subscribe and RF->IS publishing."""
    def __init__(self, call: str, passcode: str, host: str, port: int, events: queue.Queue,
                 subscription: str = ''):
        super().__init__(name="APRS-IS", daemon=True)
        self.call, self.passcode, self.host, self.port, self.events = call, passcode, host, port, events
        self.stop = threading.Event()
        self.outgoing = queue.Queue(maxsize=200)
        self.connected = threading.Event()
        self._position_lock = threading.Lock()
        self.position_line = None  # station-originated APRS-IS beacon, never RF
        self.position_interval = 30*60
        self.last_beacon_at = float('-inf')
        self.last_beacon_line = None
        self.connection_epoch = 0
        if not isinstance(subscription, str) or len(subscription) > 230 or any(c in subscription for c in '\r\n'):
            raise ValueError('Invalid APRS-IS subscription')
        self.subscription = subscription
        self.incoming_dropped = 0
        self.received_lines = 0
        self._incoming_buffer = b''

    def configure_position(self, line: str | None, every_minutes: int = 30):
        if line and ('\r' in line or '\n' in line):
            raise ValueError('Neplatný APRS-IS beacon')
        if not 30 <= every_minutes <= 120:
            raise ValueError('Maják APRS-IS lze odesílat nejvýše jednou za 30 min.')
        with self._position_lock:
            self.position_line = line
            self.position_interval = every_minutes*60
            if line != self.last_beacon_line:
                self.last_beacon_at = float('-inf')

    def emit(self, event, data):
        try:
            self.events.put_nowait((-1, event, data))
        except queue.Full:
            # Never let Internet traffic stall the local APRS RX or TNC.
            self.incoming_dropped += 1

    def _receive_feed(self, data: bytes):
        """Incrementally parse APRS-IS lines; discard overlong/invalid lines."""
        self._incoming_buffer += data
        if len(self._incoming_buffer) > 16384:
            self._incoming_buffer = b''  # Fail closed if a server sends huge lines.
            self.incoming_dropped += 1
            return
        while b'\n' in self._incoming_buffer:
            raw, self._incoming_buffer = self._incoming_buffer.split(b'\n', 1)
            raw = raw.rstrip(b'\r')
            if not raw or raw.startswith(b'#'):
                continue
            if len(raw) > 400:
                self.incoming_dropped += 1
                continue
            self.received_lines += 1
            self.emit('igate_received', raw.decode('latin-1', errors='replace'))

    def enqueue(self, line: str) -> bool:
        if not self.connected.is_set() or self.stop.is_set(): return False
        try:
            self.outgoing.put_nowait((time.monotonic(), line))
            return True
        except queue.Full:
            self.emit("igate_error", "Fronta APRS-IS plná (200), rámec zahozen")
            return False

    def enqueue_local(self, line: str, kind: str = 'telemetry') -> bool:
        if kind not in ('telemetry', 'digi_beacon'):
            raise ValueError('Unknown APRS-IS local packet type')
        if not self.connected.is_set() or self.stop.is_set() or any(c in line for c in '\r\n'):
            return False
        try:
            line.encode('ascii')
            self.outgoing.put_nowait((time.monotonic(), line, kind))
            return True
        except (queue.Full, UnicodeEncodeError):
            self.emit('igate_error', 'APRS-IS local telemetry/beacon queue full or invalid')
            return False

    def run(self):
        backoff = 3
        while not self.stop.is_set():
            conn = None
            self.connected.clear()
            try:
                self.emit("igate_status", f"Připojuji {self.host}:{self.port} ...")
                conn = socket.create_connection((self.host,self.port),timeout=8)
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                conn.settimeout(1.0)
                # Read server banner when available, then send login.
                try: conn.recv(2048)
                except socket.timeout: pass
                sub = ' filter ' + self.subscription if self.subscription else ''
                login = f"user {self.call} pass {self.passcode} vers OK5TVR-KISS 1.7{sub}\r\n"
                conn.sendall(login.encode("ascii"))
                buffer = b""
                verified = False
                deadline = time.monotonic() + 12
                while not self.stop.is_set() and time.monotonic() < deadline:
                    try: block = conn.recv(4096)
                    except socket.timeout: continue
                    if not block: raise ConnectionError("Server ukončil spojení při přihlášení")
                    buffer += block
                    if len(buffer) > 100000: buffer = buffer[-5000:]
                    while b"\n" in buffer:
                        rawline, buffer = buffer.split(b"\n", 1)
                        line = rawline.decode("ascii", "replace").strip()
                        if line.lower().startswith("# logresp"):
                            verified = bool(re.search(r"\bverified\b",line,re.I))
                            if not verified:
                                self.emit("igate_error", f"APRS-IS odmítl přihlášení: {line[:160]}")
                                return
                            break
                    if verified: break
                if not verified: raise ConnectionError("APRS-IS nepotvrdil ověřené přihlášení")
                self._incoming_buffer = b''
                if buffer:
                    self._receive_feed(buffer)
                self.connected.set()
                self.connection_epoch += 1
                self.emit("igate_status", f"Online: {self.call} @ {self.host}:{self.port}")
                backoff = 3
                # Keep server socket alive and drain a few queued RF frames per cycle.
                while not self.stop.is_set():
                    with self._position_lock:
                        posline = self.position_line
                        interval = self.position_interval
                        should_beacon = bool(posline and (posline != self.last_beacon_line
                                                   or time.monotonic() - self.last_beacon_at >= interval))
                    if should_beacon:
                        conn.sendall(posline.encode('ascii')+b'\r\n')
                        with self._position_lock:
                            self.last_beacon_at = time.monotonic()
                            self.last_beacon_line = posline
                        self.emit('igate_beacon', posline[:110])
                    for _ in range(6):
                        try: event = self.outgoing.get_nowait()
                        except queue.Empty: break
                        created, line = event[:2]
                        kind = event[2] if len(event) == 3 else 'rf_forward'
                        if time.monotonic() - created > 60: continue
                        conn.sendall(line.encode('latin-1') + b'\r\n')
                        if kind == 'rf_forward':
                            self.emit('igate_sent', line[:100])
                        else:
                            self.emit('igate_local_sent', {'kind': kind, 'line': line[:110]})
                    try:
                        got = conn.recv(2048)
                        if not got: raise ConnectionError("APRS-IS odpojil spojení")
                        self._receive_feed(got)
                    except socket.timeout:
                        pass
            except Exception as exc:
                if not self.stop.is_set(): self.emit("igate_status", f"Odpojeno: {str(exc)[:120]}")
            finally:
                self.connected.clear()
                if conn:
                    try: conn.close()
                    except OSError: pass
            if not self.stop.is_set():
                self.stop.wait(backoff)
                backoff = min(60,backoff*2)
        self.emit("igate_status", "Vypnuto")
