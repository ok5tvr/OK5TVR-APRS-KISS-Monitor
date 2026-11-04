"""Secure-by-default read-only APRS map and optional headless admin panel.

Map remains offline-capable; no third-party JS/WebGL. Remote LAN access is opt-in.
Admin needs an independent random capability token PLUS an explicit action.
Never expose APRS-IS passcode or radio TX on the read-only dashboard.
"""
from __future__ import annotations
import json
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

_ASSET_DIR = Path(__file__).resolve().parent
HTML = (_ASSET_DIR / 'web_dashboard.html').read_text(encoding='utf-8')
ADMIN_HTML = (_ASSET_DIR / 'web_control.html').read_text(encoding='utf-8') if (_ASSET_DIR / 'web_control.html').exists() else ''
MESSAGES_HTML = (_ASSET_DIR / 'web_messages.html').read_text(encoding='utf-8') if (_ASSET_DIR / 'web_messages.html').exists() else ''


class WebPanel:
    def __init__(self, state, operator=None, viewer_token=None, admin_token=None):
        self.state = state
        self.operator = operator
        self.httpd = None
        self.thread = None
        self.lan = False
        self.token = viewer_token or secrets.token_urlsafe(32)
        self.admin_token = admin_token or secrets.token_urlsafe(32)
        self.port = 8765

    def start(self, lan=False, port=8765, fallback=True):
        self.close()
        state, operator = self.state, self.operator
        viewer_key, admin_key, allow_lan = self.token, self.admin_token, lan

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Never write bearer tokens to access logs.

            def _allowed_viewer(self, parsed):
                if self.client_address[0] in ('127.0.0.1', '::1'):
                    return True
                return allow_lan and (
                    secrets.compare_digest(parse_qs(parsed.query).get('key', [''])[0], viewer_key)
                    or secrets.compare_digest(parse_qs(parsed.query).get('admin', [''])[0], admin_key)
                )

            def _allowed_admin(self, parsed):
                if operator is None:
                    return False
                if not allow_lan and self.client_address[0] not in ('127.0.0.1', '::1'):
                    return False
                return secrets.compare_digest(
                    parse_qs(parsed.query).get('admin', [''])[0], admin_key)

            def _respond(self, code, contents, mime='application/json; charset=utf-8', cache='no-store'):
                if isinstance(contents, str):
                    contents = contents.encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(contents)))
                self.send_header('Cache-Control', cache)
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('X-Frame-Options', 'DENY')
                self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
                self.send_header('Content-Security-Policy',
                                 "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                                 "style-src 'self' 'unsafe-inline'; img-src 'self' data: https://basemaps.cartocdn.com; "
                                 "connect-src 'self'; frame-ancestors 'none'")
                self.end_headers()
                try:
                    self.wfile.write(contents)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    pass

            def do_GET(self):
                parsed = urlsplit(self.path)
                if parsed.path in ('/control', '/api/config', '/messages', '/api/messages'):
                    if not self._allowed_admin(parsed):
                        self._respond(403, '{"error":"Vyžadován administrátorský odkaz."}')
                        return
                    if parsed.path == '/control':
                        self._respond(200, ADMIN_HTML, 'text/html; charset=utf-8')
                    elif parsed.path == '/messages':
                        self._respond(200, MESSAGES_HTML, 'text/html; charset=utf-8')
                    elif parsed.path == '/api/messages':
                        self._respond(200, json.dumps(operator.messages_snapshot(), ensure_ascii=False))
                    else:
                        self._respond(200, json.dumps(operator.public_config(), ensure_ascii=False))
                    return
                if not self._allowed_viewer(parsed):
                    self._respond(403, '{"error":"Přístup pouze z lokální/LAN sítě s klíčem."}')
                    return
                if parsed.path == '/':
                    self._respond(200, HTML, 'text/html; charset=utf-8')
                elif parsed.path == '/api/state':
                    self._respond(200, json.dumps(state.snapshot(), ensure_ascii=False))
                elif parsed.path == '/assets/offline_geography.json':
                    try:
                        contents = (_ASSET_DIR / 'offline_geography.json').read_bytes()
                    except OSError:
                        self._respond(404, '{"error":"Chybí offline geografie."}')
                        return
                    self._respond(200, contents, 'application/json; charset=utf-8', 'private, max-age=3600')
                elif parsed.path == '/favicon.ico':
                    self._respond(204, b'', 'image/x-icon')
                else:
                    self._respond(404, '{"error":"Neznámá cesta."}')

            def do_POST(self):
                parsed = urlsplit(self.path)
                if parsed.path != '/api/control' or operator is None:
                    self._respond(404, '{"error":"Neznámá cesta."}')
                    return
                if not allow_lan and self.client_address[0] not in ('127.0.0.1', '::1'):
                    self._respond(403, '{"error":"LAN je vypnutá."}')
                    return
                # Token must be sent in a non-simple custom header: cross-site
                # forms cannot trigger actions; the server has no CORS support.
                if not secrets.compare_digest(self.headers.get('X-APRS-Admin', ''), admin_key):
                    self._respond(403, '{"error":"Neplatný administrátorský klíč."}')
                    return
                origin = self.headers.get('Origin', '')
                expected = f'http://{self.headers.get("Host", "")}'
                if origin and origin != expected:
                    self._respond(403, '{"error":"Cizí Origin je zakázaný."}')
                    return
                if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
                    self._respond(415, '{"error":"Vyžaduji application/json."}')
                    return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 8192:
                        raise ValueError('Tělo požadavku musí mít 1–8192 B.')
                    payload = json.loads(self.rfile.read(length).decode('utf-8'))
                    if not isinstance(payload, dict):
                        raise ValueError('Čekám objekt JSON.')
                    action = payload.pop('action', '')
                    if not isinstance(action, str):
                        raise ValueError('Neplatná akce.')
                    result = operator.command(action, payload)
                    self._respond(200, json.dumps({'ok': True, 'result': result}, ensure_ascii=False))
                except (ValueError, TypeError) as exc:
                    self._respond(400, json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
                except TimeoutError:
                    self._respond(503, '{"ok":false,"error":"Služba neodpovídá."}')

        addr = '0.0.0.0' if lan else '127.0.0.1'
        try:
            self.httpd = ThreadingHTTPServer((addr, port), Handler)
        except OSError:
            if port == 0 or not fallback:
                raise
            self.httpd = ThreadingHTTPServer((addr, 0), Handler)
        self.httpd.daemon_threads = True
        self.httpd.allow_reuse_address = True
        self.port = self.httpd.server_address[1]
        self.lan = lan
        self.thread = threading.Thread(target=self.httpd.serve_forever, name='APRS-web', daemon=True)
        self.thread.start()
        return self.port

    def close(self):
        if self.httpd:
            old = self.httpd
            self.httpd = None
            old.shutdown()
            old.server_close()
        self.thread = None

    def local_url(self):
        return f'http://127.0.0.1:{self.port}/'

    def lan_url(self, host):
        return f'http://{host}:{self.port}/?key={self.token}'

    def admin_url(self, host):
        return f'http://{host}:{self.port}/control?admin={self.admin_token}'


def local_ipv4():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(('192.0.2.1', 80))
            return sock.getsockname()[0]
        finally:
            sock.close()
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return 'IP_TVEHO_PC'
