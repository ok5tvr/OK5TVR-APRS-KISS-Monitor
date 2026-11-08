#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Common KISS/AX.25 APRS protocol for desktop and Raspberry Pi headless service."""
from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import datetime
from aprs_features import parse_position

FEND, FESC, TFEND, TFESC = 0xC0, 0xDB, 0xDC, 0xDD
MAX_KISS_FRAME = 4096

class KissDecoder:
    """Incrementally decode KISS byte-stream frames; accepts arbitrary USB chunks."""

    def __init__(self):
        self.started = False
        self.escaped = False
        self.invalid = False
        self.buffer = bytearray()
        self.errors = 0

    def feed(self, chunk: bytes) -> list[bytes]:
        packets = []
        for ch in chunk:
            if ch == FEND:
                if self.started and self.buffer:
                    if not self.invalid and not self.escaped:
                        packets.append(bytes(self.buffer))
                    else:
                        self.errors += 1
                self.started = True
                self.escaped = False
                self.invalid = False
                self.buffer.clear()
                continue

            if not self.started:
                continue
            if self.invalid:
                continue
            if self.escaped:
                if ch == TFEND:
                    self.buffer.append(FEND)
                elif ch == TFESC:
                    self.buffer.append(FESC)
                else:
                    self.invalid = True
                self.escaped = False
            elif ch == FESC:
                self.escaped = True
            else:
                self.buffer.append(ch)
            if len(self.buffer) > MAX_KISS_FRAME:
                self.invalid = True
        return packets


def display_bytes(value: bytes) -> str:
    """Show standard APRS ASCII plus escaped control/non-ASCII bytes."""
    return "".join(chr(c) if 32 <= c <= 126 else ("\\r" if c == 13 else "\\n" if c == 10 else f"\\x{c:02X}") for c in value)


def parse_address(value: bytes, repeater: bool = False) -> str:
    if len(value) != 7:
        raise ValueError("Nekompletní AX.25 adresa")
    call = "".join(chr(b >> 1) for b in value[:6]).strip()
    if not call or not all(ch.isalnum() or ch == "-" for ch in call):
        raise ValueError("Neplatná AX.25 značka")
    ssid = (value[6] >> 1) & 15
    name = f"{call}-{ssid}" if ssid else call
    if repeater and value[6] & 0x80:
        name += "*"
    return name


def position_summary(data: bytes) -> str | None:
    """Decode basic uncompressed APRS position; do not guess compressed/Mic-E."""
    if not data or data[:1] not in (b"!", b"=", b"/", b"@"):
        return None
    # / and @ formats carry a 7-character time stamp after the type byte.
    payload = data[8:] if data[0] in (ord('/'), ord('@')) else data[1:]
    if len(payload) < 19:
        return None
    latitude = re.fullmatch(rb"(\d{2})(\d{2}\.\d{2})([NS])", payload[:8])
    longitude = re.fullmatch(rb"(\d{3})(\d{2}\.\d{2})([EW])", payload[9:18])
    if not latitude or not longitude:
        return None
    lat_deg = int(latitude.group(1))
    lon_deg = int(longitude.group(1))
    lat_min = float(latitude.group(2))
    lon_min = float(longitude.group(2))
    if lat_deg > 90 or lon_deg > 180 or lat_min >= 60 or lon_min >= 60:
        return None
    lat = (lat_deg + lat_min / 60) * (-1 if latitude.group(3) == b"S" else 1)
    lon = (lon_deg + lon_min / 60) * (-1 if longitude.group(3) == b"W" else 1)
    comment = display_bytes(payload[19:])
    return f"GPS {lat:.5f}, {lon:.5f}" + (f" | {comment}" if comment else "")


def classify_aprs(data: bytes) -> tuple[str, str]:
    if not data:
        return "AX.25", "(prázdný obsah)"
    text = display_bytes(data)
    pos = position_summary(data)
    if pos:
        return "Pozice", pos
    if data.startswith(b":") and len(data) >= 11 and data[10:11] == b":":
        addressee = display_bytes(data[1:10]).strip()
        return "Zpráva", f"Komu {addressee}: {display_bytes(data[11:])}"
    if data.startswith(b"> ") or data.startswith(b">"):
        return "Stav", display_bytes(data[1:])
    if data.startswith(b"T#"):
        return "Telemetrie", text
    if data.startswith(b"_"):
        return "Počasí", text
    if data.startswith(b"$"):
        return "NMEA GPS", text
    if data.startswith(b";"):
        return "Objekt", text
    if data.startswith(b")"):
        return "Položka", text
    if data.startswith((b"`", b"'")):
        return "Mic-E", text
    if data.startswith(b"}"):
        return "3rd-party", text
    if data.startswith((b"!", b"=", b"/", b"@")):
        return "Pozice", text
    return "APRS", text


@dataclass
class Packet:
    timestamp: str
    source: str
    destination: str
    path: str
    kind: str
    summary: str
    payload: str
    hex_data: str
    simulated: bool = False
    latitude: float | None = None
    longitude: float | None = None
    position_label: str | None = None
    position_source: str | None = None
    position_format: str | None = None
    symbol: str | None = None
    heard_direct: bool | None = None
    control: int | None = None
    pid: int | None = None
    raw_info: bytes = b""
    raw_ax25: bytes = b""


def decode_ax25(raw: bytes, simulated: bool = False) -> Packet:
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    hexdump = raw.hex(" ").upper()
    try:
        if len(raw) < 16:
            raise ValueError("Příliš krátký AX.25 rámec")
        offset = 0
        addresses = []
        for index in range(10):
            if offset + 7 > len(raw):
                raise ValueError("Nekompletní seznam AX.25 adres")
            address = raw[offset:offset + 7]
            addresses.append(parse_address(address, repeater=index >= 2))
            offset += 7
            if address[6] & 1:
                break
        else:
            raise ValueError("Příliš mnoho AX.25 adres")
        if len(addresses) < 2 or offset >= len(raw):
            raise ValueError("Chybí zdrojová adresa nebo control field")
        dst, src = addresses[0], addresses[1]
        # TNC2 convention: only the LAST used DIGI gets a visible *.
        # AX.25 retains H bits on every preceding used address on the wire.
        hops = addresses[2:]
        used = [i for i,x in enumerate(hops) if x.endswith('*')]
        if used:
            hops = [x.rstrip('*') if i != used[-1] else x for i,x in enumerate(hops)]
        path = ",".join(hops)
        # The AX.25 H-bit is authoritative for whether an RF frame was
        # digipeated. An unused WIDE1-1 in the path does NOT make it VIA.
        repeated_by_digi = any(raw[20+i*7] & 0x80 for i in range(len(addresses)-2))
        control = raw[offset]
        pid = None
        if control == 0x03 and offset + 1 < len(raw):
            pid = raw[offset + 1]
            info = raw[offset + 2:]
            if pid == 0xF0:
                kind, summary = classify_aprs(info)
            else:
                kind, summary = f"UI PID {pid:02X}", display_bytes(info)
        elif control & 1 == 0:
            kind, summary = "AX.25 I", display_bytes(raw[offset + 1:])
            info = raw[offset + 1:]
        else:
            kind, summary = f"AX.25 {control:02X}", display_bytes(raw[offset + 1:])
            info = raw[offset + 1:]
        packet = Packet(timestamp, src, dst, path, kind, summary, display_bytes(info), hexdump, simulated,
                        control=control, pid=pid, raw_info=info)
        packet.heard_direct = (not repeated_by_digi and not info.startswith(b'}')) if control == 0x03 and pid == 0xF0 else None
        packet.raw_ax25 = raw
        if control == 0x03 and pid == 0xF0:
            pos = parse_position(info, dst)
            if pos:
                packet.latitude, packet.longitude = pos["lat"], pos["lon"]
                packet.position_label = pos.get("label")
                packet.position_source = pos.get('source')
                packet.position_format = pos['format']
                packet.symbol = pos.get('symbol')
                if "GPS " not in packet.summary:
                    packet.summary = (f"GPS {packet.latitude:.5f}, {packet.longitude:.5f}"
                                      f" ({pos['format']}) | {packet.summary[:110]}")
        return packet
    except ValueError as exc:
        return Packet(timestamp, "?", "?", "", "RAW", f"{exc}: {display_bytes(raw)}", display_bytes(raw), hexdump, simulated)


def demo_ax25_packet() -> bytes:
    """Generate a synthetic (non-RF) UI AX.25 position frame for UI testing."""
    def address(call: str, ssid: int, last: bool) -> bytes:
        call = call.ljust(6)
        return bytes([ord(ch) << 1 for ch in call]) + bytes([0x60 | (ssid << 1) | (1 if last else 0)])
    return (address("APRS", 0, False) + address("TEST", 7, False)
            + address("WIDE1", 1, True)
            + b"\x03\xF0!4903.50N/01322.00E>DEMO - test bez RF")


