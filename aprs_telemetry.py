"""Standard APRS telemetry and bounded, 15-minute radio statistics.

Payload generation is side-effect-free. The service may transmit on APRS-IS, or for DIGI after explicit confirmation via KISS RF.
No GPS position implies no distance sample; this is NOT a propagation measurement.
"""
from __future__ import annotations

from collections import deque
import math
import re
import threading
import time

OVERLAY_RE = re.compile(r"[A-Z0-9]\Z", re.ASCII)


def symbol_code(table: str, symbol: str, overlay: str = '') -> str:
    """Return APRS wire symbol code (table-or-overlay + symbol byte)."""
    if table not in ('/', '\\') or not isinstance(symbol, str) or len(symbol) != 1 or not 33 <= ord(symbol) <= 126:
        raise ValueError('Invalid APRS symbol/table.')
    if not isinstance(overlay, str) or (overlay and not OVERLAY_RE.fullmatch(overlay)):
        raise ValueError('APRS overlay must be A-Z, 0-9 or empty.')
    if overlay and table != '\\':
        raise ValueError('Overlay requires the alternate symbol table.')
    return (overlay or table) + symbol


def great_circle_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between *reported* station positions."""
    inputs = (lat1, lon1, lat2, lon2)
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in inputs):
        raise ValueError('Invalid geographical coordinate.')
    if abs(lat1) > 90 or abs(lat2) > 90 or abs(lon1) > 180 or abs(lon2) > 180:
        raise ValueError('Coordinate out of range.')
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(a)))


class RadioWindow:
    """Rolling fifteen-minute counters. One sample per unique station for distance.

    Metrics count KISS *decoded frames* and USB TNC writes, not confirmed RF
    demodulation or over-the-air transmissions. Up to 50k events are retained.
    """
    WINDOW = 15 * 60
    MAX_EVENTS = 50000

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.rx = deque(maxlen=self.MAX_EVENTS)
        self.tx = deque(maxlen=self.MAX_EVENTS)
        self.gated = deque(maxlen=self.MAX_EVENTS)
        self.errors = deque(maxlen=self.MAX_EVENTS)
        self.dropped_events = 0

    def _append(self, q, payload):
        if len(q) == q.maxlen:
            self.dropped_events += 1
        q.append((self.clock(), *payload))

    def record_rx(self, call, latitude=None, longitude=None, own_position=None, position_label=None):
        distance = None
        if (not position_label and own_position and latitude is not None and longitude is not None):
            try:
                distance = great_circle_km(own_position[0], own_position[1], latitude, longitude)
            except (ValueError, TypeError):
                pass
        with self.lock:
            self._append(self.rx, (str(call).upper(), distance))

    def record_tx(self, category='unknown'):
        with self.lock:
            self._append(self.tx, (str(category),))

    def record_gate(self):
        with self.lock:
            self._append(self.gated, ())

    def record_tx_error(self):
        with self.lock:
            self._append(self.errors, ())

    def _trim(self, now):
        for q in (self.rx, self.tx, self.gated, self.errors):
            while q and now - q[0][0] >= self.WINDOW:
                q.popleft()

    def snapshot(self):
        with self.lock:
            now = self.clock()
            self._trim(now)
            stations = {call for _, call, _ in self.rx if call and call != '?'}
            # Latest announced position per callsign: repeated beacons do not
            # bias the average, and third-party APRS objects are excluded.
            locations = {}
            for _, call, km in self.rx:
                if call not in ('', '?') and km is not None:
                    locations[call] = km
            avg = sum(locations.values()) / len(locations) if locations else None
            dx_call, dx = max(locations.items(), key=lambda item: item[1]) if locations else ('', None)
            return dict(window_minutes=15, rx_packets=len(self.rx), tx_packets=len(self.tx),
                        unique_stations=len(stations), positioned_stations=len(locations),
                        avg_distance_km=round(avg, 1) if avg is not None else None,
                        dx_max_km=round(dx, 1) if dx is not None else None, dx_callsign=dx_call,
                        igate_forwarded=len(self.gated),
                        digi_tx=sum(category == 'digi' for _, category in self.tx),
                        rx_per_min=round(len(self.rx) / 15, 2),
                        tx_per_min=round(len(self.tx) / 15, 2),
                        forwarded_fraction_pct=round(100 * len(self.gated) / len(self.rx), 1) if self.rx else None,
                        tx_errors=len(self.errors), dropped_samples=self.dropped_events,
                        sample_notice='Distance from own configured GPS to latest decoded station positions, not measured RF range.')


def _int8(value):
    # APRS 1.0 telemetry numeric channels: 0-255; saturation is explicit on web.
    if value is None:
        return 0
    return min(255, max(0, int(round(value))))


def telemetry_data_payload(sequence: int, metrics: dict, role: str, flags: dict) -> str:
    """APRS 1.0 (not compressed) T# payload with five 8-bit analog channels."""
    if role not in ('igate', 'digi'):
        raise ValueError('Unknown telemetry role.')
    if type(sequence) is not int or not 0 <= sequence <= 999:
        raise ValueError('APRS telemetry sequence must be 0..999')
    a = [metrics['rx_packets'], metrics['tx_packets'], metrics['avg_distance_km'],
         metrics['unique_stations'], metrics['igate_forwarded' if role == 'igate' else 'digi_tx']]
    bits = ''.join('1' if flags.get(x, False) else '0' for x in
                   ('usb', 'aprsis', 'digi', 'heard', 'tx_error', 'gps', 'telemetry', 'reserved'))
    return 'T#' + f'{sequence:03d}' + ',' + ','.join(f'{_int8(v):03d}' for v in a) + ',' + bits


def metadata_payloads(role: str) -> tuple[str, str, str, str]:
    """Standard PARM/UNIT/EQNS/BITS data fields, addressed to telemetry sender."""
    if role not in ('igate', 'digi'):
        raise ValueError('Unknown telemetry role.')
    last = 'Gate' if role == 'igate' else 'Digi'
    return (f'PARM.RX15m,TX15m,AvgKm,Unique,{last},USB,IS,Digi,Heard,TxErr,GPS,Tel',
            'UNIT.pkt,pkt,km,stn,pkt',
            'EQNS.' + ','.join(('0', '1', '0') * 5),
            'BITS.11111111,OK5TVR ' + ('iGate' if role == 'igate' else 'DIGI'))


def aprsis_telemetry_lines(call: str, seq: int, metrics: dict, role: str, flags: dict,
                            metadata=False) -> list[str]:
    from aprs_features import CALL_RE
    call = str(call).upper()
    if not CALL_RE.fullmatch(call):
        raise ValueError('Invalid telemetry source callsign')
    header = f'{call}>APZKIS,TCPIP*:'
    lines = []
    if metadata:
        for item in metadata_payloads(role):
            if len(item) > 67:
                raise ValueError('APRS telemetry metadata too long')
            lines.append(header + f':{call:<9}:' + item)
    lines.append(header + telemetry_data_payload(seq, metrics, role, flags))
    return lines
