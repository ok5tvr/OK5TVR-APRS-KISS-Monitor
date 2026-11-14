"""TCP KISS transport and safe shared serial-to-network KISS hub.

No DSP modem, no extra serial port opened. Public/LAN TCP clients are RX-only.
Optional network-to-RF transmission is loopback-only and operator-enabled.
"""
from __future__ import annotations

import ipaddress
import queue
import socket
import threading
import time

from aprs_features import encode_kiss_data
from aprs_protocol import KissDecoder, decode_ax25
from aprs_rf_scheduler import RFOutputScheduler


class TCPKissReader(threading.Thread):
    """Outgoing TCP KISS client; same event / send interface as SerialReader."""

    def __init__(self, host, port, events, stop, session):
        super().__init__(name="KISS-tcp-reader", daemon=True)
        self.host = host
        self.port = f"{host}:{port}"
        self.tcp_port = port
        self.events = events
        self.stop = stop
        self.session = session
        self.digi_allowed = threading.Event()
        self.isrf_allowed = threading.Event()  # OFF unless explicitly enabled by admin
        self.outgoing = RFOutputScheduler()  # single bounded queue for every TX category
        self.connected = False
        self.last_error = ''

    def emit(self, kind, data):
        try:
            self.events.put_nowait((self.session, kind, data))
        except queue.Full:
            pass

    def send(self, encoded_kiss, category='manual'):
        if self.stop.is_set() or not self.connected or (category == 'igate_is_to_rf' and not self.isrf_allowed.is_set()):
            return False
        try:
            self.outgoing.put_nowait((bytes(encoded_kiss), category))
            return True
        except queue.Full:
            return False

    def run(self):
        decoder = KissDecoder()
        last_errors = 0
        try:
            # Explicit timeout allows quick shutdown and reconnection attempts.
            with socket.create_connection((self.host, self.tcp_port), timeout=3.0) as conn:
                conn.settimeout(0.2)
                self.connected = True
                self.emit('connected', self.port)
                while not self.stop.is_set():
                    try:
                        payload, category = self.outgoing.get_nowait()
                    except queue.Empty:
                        payload = None
                    if payload is not None:
                        if category in ('digi', 'telemetry_rf', 'digi_beacon_rf') and not self.digi_allowed.is_set():
                            self.emit('tx_cancelled', 'RF DIGI permission revoked')
                            continue
                        if category == 'igate_is_to_rf' and not self.isrf_allowed.is_set():
                            self.emit('tx_cancelled', 'IS->RF disabled: pending packet cancelled')
                            continue
                        try:
                            conn.sendall(payload)
                            self.emit('tx_written', {'bytes': len(payload), 'category': category})
                        except OSError as exc:
                            self.emit('tx_error', {'error': str(exc), 'category': category})
                            raise
                    try:
                        chunk = conn.recv(512)
                    except socket.timeout:
                        continue
                    if not chunk:
                        raise ConnectionError('TCP KISS server disconnected')
                    for item in decoder.feed(chunk):
                        if not item:
                            continue
                        if item[0] != 0:
                            self.emit('control', 'TCP KISS: non-data command discarded')
                            continue
                        if len(item) < 2:
                            self.emit('invalid', 'TCP KISS: empty frame')
                        else:
                            self.emit('frame', decode_ax25(item[1:]))
                    if decoder.errors > last_errors:
                        self.emit('invalid', f'TCP KISS framing errors: {decoder.errors - last_errors}')
                        last_errors = decoder.errors
        except (OSError, ConnectionError) as exc:
            self.last_error = str(exc)
            if not self.stop.is_set():
                self.emit('error', f'TCP KISS {self.port}: {exc}')
        finally:
            self.connected = False
            self.emit('closed', '')


class TCPKissHub:
    """Fan out received RF AX.25 frames to TCP KISS consumers.

    Bounded queues protect low-power Raspberry Pi from slow consumers.
    Clients never get the physical serial interface and cannot transmit
    unless loopback TX was explicitly enabled by the administrator.
    """

    def __init__(self, host='127.0.0.1', port=8001, allow_tx=False, tx_request=None):
        self.host, self.port = host, int(port)
        if allow_tx and host != '127.0.0.1':
            raise ValueError('TCP KISS TX can only be enabled on loopback')
        self.allow_tx = bool(allow_tx)
        self.tx_request = tx_request
        self.stop_event = threading.Event()
        self.server = None
        self.thread = None
        self.lock = threading.RLock()
        self.clients = {}
        self.next_client = 0
        self.published = 0
        self.dropped = 0
        self.client_tx_accepted = 0
        self.client_tx_rejected = 0
        self.last_error = ''
        self.last_tx = 0.0

    def start(self):
        if self.thread is not None:
            return
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((self.host, self.port))
            server.listen(8)
            server.settimeout(0.3)
            self.server = server
            self.port = server.getsockname()[1]
            self.thread = threading.Thread(target=self._accept, name='KISS-tcp-hub', daemon=True)
            self.thread.start()
        except BaseException:
            server.close()
            raise

    def _accept(self):
        while not self.stop_event.is_set():
            try:
                conn, address = self.server.accept()
                conn.settimeout(0.2)
            except socket.timeout:
                continue
            except OSError:
                break
            with self.lock:
                if len(self.clients) >= 8:
                    conn.close()
                    self.dropped += 1
                    continue
                self.next_client += 1
                client_id = self.next_client
                outbound = queue.Queue(maxsize=64)
                self.clients[client_id] = (conn, outbound)
            threading.Thread(target=self._serve_client, args=(client_id, address),
                             name=f'KISS-hub-{client_id}', daemon=True).start()

    def _serve_client(self, client_id, address):
        with self.lock:
            conn, outbound = self.clients[client_id]
        decoder = KissDecoder()
        try:
            while not self.stop_event.is_set():
                try:
                    frame = outbound.get_nowait()
                except queue.Empty:
                    frame = None
                if frame:
                    conn.sendall(frame)
                try:
                    chunk = conn.recv(1024)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                for item in decoder.feed(chunk):
                    if not item or item[0] != 0 or len(item) < 17:
                        continue
                    if not (self.allow_tx and address[0] == '127.0.0.1' and self.tx_request):
                        with self.lock:
                            self.client_tx_rejected += 1
                        continue
                    # No connected-mode, non-APRS PID, or malformed RF from clients.
                    ax = item[1:]
                    decoded = decode_ax25(ax)
                    if (len(ax) > 330 or decoded.source == '?' or
                            decoded.control != 0x03 or decoded.pid != 0xF0):
                        with self.lock:
                            self.client_tx_rejected += 1
                        continue
                    now = time.monotonic()
                    with self.lock:
                        if now - self.last_tx < 3.0:
                            self.client_tx_rejected += 1
                            continue
                        self.last_tx = now
                    try:
                        accepted = bool(self.tx_request(encode_kiss_data(ax)))
                    except (OSError, TimeoutError, ValueError):
                        accepted = False
                    with self.lock:
                        if accepted:
                            self.client_tx_accepted += 1
                        else:
                            self.client_tx_rejected += 1
        except OSError as exc:
            self.last_error = str(exc)[:160]
        finally:
            with self.lock:
                self.clients.pop(client_id, None)
            try:
                conn.close()
            except OSError:
                pass

    def publish(self, ax25):
        if not isinstance(ax25, bytes) or not ax25 or self.stop_event.is_set():
            return
        frame = encode_kiss_data(ax25)
        with self.lock:
            self.published += 1
            for _, outbound in self.clients.values():
                try:
                    outbound.put_nowait(frame)
                except queue.Full:
                    self.dropped += 1

    def snapshot(self):
        with self.lock:
            return {'running': bool(self.thread and self.thread.is_alive()),
                    'host': self.host, 'port': self.port,
                    'clients': len(self.clients), 'rx_only': not self.allow_tx,
                    'frames_published': self.published, 'frames_dropped': self.dropped,
                    'tx_accepted': self.client_tx_accepted, 'tx_rejected': self.client_tx_rejected,
                    'last_error': self.last_error}

    def close(self):
        self.stop_event.set()
        if self.server:
            try:
                self.server.close()
            except OSError:
                pass
        with self.lock:
            clients = list(self.clients.values())
            self.clients.clear()
        for conn, _ in clients:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(timeout=1.0)
        self.thread = None
