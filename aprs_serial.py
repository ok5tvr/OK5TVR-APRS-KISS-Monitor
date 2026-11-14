#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared USB KISS serial reader/writer for Windows and Linux."""
from __future__ import annotations
import queue
import threading
try:
    import serial
except ImportError:
    serial = None
from aprs_protocol import KissDecoder, decode_ax25

class SerialReader(threading.Thread):
    def __init__(self, port: str, baud: int, events: queue.Queue, stop: threading.Event, session: int):
        super().__init__(name="KISS-serial-reader", daemon=True)
        self.port = port
        self.baud = baud
        self.events = events
        self.stop = stop
        self.session = session
        self.outgoing = queue.Queue(maxsize=1)  # Never build a TX queue in the background.
        self.digi_allowed = threading.Event()
        self.isrf_allowed = threading.Event()  # OFF unless explicitly enabled by admin  # OFF until operator starts DIGI

    def send(self, encoded_kiss: bytes, category: str = "manual") -> bool:
        if self.stop.is_set() or (
                category == 'igate_is_to_rf' and not self.isrf_allowed.is_set()):
            return False
        try:
            self.outgoing.put_nowait((encoded_kiss, category))
            return True
        except queue.Full:
            return False

    def emit(self, event_type: str, value):
        self.events.put((self.session, event_type, value))

    def run(self):
        if serial is None:
            self.emit("error", "Chybí pyserial. Spusť instalaci pomocí spustit.bat.")
            self.emit("closed", "")
            return
        decoder = KissDecoder()
        last_errors = 0
        try:
            with serial.Serial(self.port, self.baud, timeout=0.20, write_timeout=1) as conn:
                # The F4HWN USB CDC interface uses the host-open state (DTR).
                # Writes are allowed ONLY after explicit manual TX confirmation.
                conn.dtr = True
                self.emit("connected", self.port)
                while not self.stop.is_set():
                    try:
                        outgoing = self.outgoing.get_nowait()
                    except queue.Empty:
                        outgoing = None
                    if outgoing is not None and not self.stop.is_set():
                        payload, category = outgoing
                        if category in ('digi', 'telemetry_rf', 'digi_beacon_rf') and not self.digi_allowed.is_set():
                            self.emit('tx_cancelled', 'DIGI vypnuté: čekající RF DIGI/telemetrie/maják neodeslán')
                            continue
                        if category == 'igate_is_to_rf' and not self.isrf_allowed.is_set():
                            self.emit('tx_cancelled', 'IS->RF disabled: queued packet cancelled')
                            continue
                        try:
                            written = conn.write(payload)
                            conn.flush()
                            if written != len(payload):
                                raise IOError("Neúplný zápis do KISS TNC")
                            self.emit("tx_written", {"bytes":len(payload),"category":category})
                        except Exception as exc:
                            self.emit("tx_error", {"error":str(exc),"category":category})
                    fragment = conn.read(512)
                    if not fragment:
                        continue
                    for packet in decoder.feed(fragment):
                        if not packet:
                            continue
                        cmd = packet[0] & 0x0F
                        kiss_port = packet[0] >> 4
                        if cmd == 0 and kiss_port == 0:
                            if len(packet) < 2:
                                self.emit("invalid", "Prázdný KISS datový rámec")
                                continue
                            self.emit("frame", decode_ax25(packet[1:]))
                        else:
                            self.emit("control", f"Port {kiss_port}, příkaz {cmd}")
                    if decoder.errors > last_errors:
                        self.emit("invalid", f"Neplatný KISS rámec ({decoder.errors - last_errors}x)")
                        last_errors = decoder.errors
        except Exception as exc:
            if not self.stop.is_set():
                self.emit("error", str(exc))
        finally:
            self.emit("closed", "")


