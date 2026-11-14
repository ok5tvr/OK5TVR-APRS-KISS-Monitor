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
from web_auth import SessionAuth, LoginThrottle

_ASSET_DIR = Path(__file__).resolve().parent
HTML = (_ASSET_DIR / 'web_dashboard.html').read_text(encoding='utf-8')
ADMIN_HTML = (_ASSET_DIR / 'web_control.html').read_text(encoding='utf-8') if (_ASSET_DIR / 'web_control.html').exists() else ''
OPERATIONS_HTML = (_ASSET_DIR / 'web_operations.html').read_text(encoding='utf-8') if (_ASSET_DIR / 'web_operations.html').exists() else ''
MESSAGES_HTML = (_ASSET_DIR / 'web_messages.html').read_text(encoding='utf-8') if (_ASSET_DIR / 'web_messages.html').exists() else ''
LOCALE_JS = (_ASSET_DIR / 'web_locale.js').read_text(encoding='utf-8')
UNIFIED_HTML = (_ASSET_DIR / 'web_unified.html').read_text(encoding='utf-8') if (_ASSET_DIR / 'web_unified.html').exists() else ''
LOGIN_HTML = (_ASSET_DIR / 'web_login.html').read_text(encoding='utf-8') if (_ASSET_DIR / 'web_login.html').exists() else ''


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
        session_auth = SessionAuth(admin_key)
        throttle = LoginThrottle()
        login_name = str(getattr(getattr(operator, 'config', None), 'secrets', {}).get('web_username', 'ok5tvr'))

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Never write bearer tokens to access logs.

            def _signed_in(self):
                return session_auth.from_header(self.headers.get('Cookie', ''))

            def _allowed_viewer(self, parsed):
                if self.client_address[0] in ('127.0.0.1', '::1'):
                    return True
                return allow_lan and (
                    self._signed_in()
                    or secrets.compare_digest(parse_qs(parsed.query).get('key', [''])[0], viewer_key)
                    or secrets.compare_digest(parse_qs(parsed.query).get('admin', [''])[0], admin_key)
                )

            def _allowed_admin(self, parsed):
                if operator is None:
                    return False
                if not allow_lan and self.client_address[0] not in ('127.0.0.1', '::1'):
                    return False
                return self._signed_in() or secrets.compare_digest(
                    parse_qs(parsed.query).get('admin', [''])[0], admin_key)

            def _respond(self, code, contents, mime='application/json; charset=utf-8', cache='no-store', cookie=None):
                if isinstance(contents, str):
                    contents = contents.encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(contents)))
                self.send_header('Cache-Control', cache)
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('X-Frame-Options', 'SAMEORIGIN')
                self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
                self.send_header('Content-Security-Policy',
                                 "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                                 "style-src 'self' 'unsafe-inline'; img-src 'self' data: https://tile.openstreetmap.org; "
                                 "connect-src 'self'; frame-ancestors 'self'")
                if cookie is not None:
                    self.send_header('Set-Cookie', cookie)
                self.end_headers()
                try:
                    self.wfile.write(contents)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    pass

            def do_GET(self):
                parsed = urlsplit(self.path)
                # Loopback-only, read-only endpoint for the optional HDMI desktop.
                # Never return access tokens, credentials, detailed configuration,
                # or RF controls. This cannot be opened from the LAN.
                if parsed.path == '/api/local-display':
                    if self.client_address[0] not in ('127.0.0.1', '::1') or operator is None:
                        self._respond(403, '{"error":"Pouze lokalni Raspberry panel."}')
                        return
                    snapshot = state.snapshot()
                    diag = operator.diagnostics_snapshot()
                    conf = operator.config.data
                    frame_history = [
                        {k: entry.get(k) for k in ('time', 'source', 'kind', 'path', 'direct', 'summary')}
                        for entry in snapshot.get('history', [])[:8]
                        if isinstance(entry, dict) and not entry.get('demo')
                    ]
                    display = {
                        'enabled': conf.get('display', {}).get('enabled', False),
                        'usb_connected': bool(diag.get('radio_connected')),
                        'port_configured': conf['serial']['port'],
                        'port_actual': diag.get('usb_port') or '',
                        'usb_connections': diag.get('usb_connections', 0),
                        'igate_connected': bool(diag.get('igate_connected')),
                        'digi_enabled': bool(diag.get('digi', {}).get('enabled')),
                        'rx': snapshot.get('rx', 0),
                        'tx_usb': snapshot.get('tx_requests', 0),
                        'igate_sent': snapshot.get('igate_sent', 0),
                        'digi_tx': diag.get('digi', {}).get('tx_written', 0),
                        'station_count': snapshot.get('station_count', 0),
                        'last_rf_frame_utc': diag.get('last_rf_frame_utc'),
                        'history': frame_history,
                    }
                    self._respond(200, json.dumps(display, ensure_ascii=False))
                    return
                if parsed.path == '/login':
                    if operator is None:
                        self._respond(404, '{"error":"Admin panel disabled"}')
                    elif self._signed_in():
                        self.send_response(302)
                        self.send_header('Location', '/app')
                        self.send_header('Content-Length', '0')
                        self.send_header('Cache-Control', 'no-store')
                        self.end_headers()
                    else:
                        self._respond(200, LOGIN_HTML, 'text/html; charset=utf-8')
                    return
                if parsed.path == '/api/session':
                    self._respond(200, json.dumps({'authenticated': self._allowed_admin(parsed),
                        'username': login_name if self._allowed_admin(parsed) else None}))
                    return
                if parsed.path == '/' and operator is not None and not parse_qs(parsed.query).get('key'):
                    if self._allowed_admin(parsed):
                        self._respond(200, UNIFIED_HTML, 'text/html; charset=utf-8')
                    else:
                        self.send_response(302)
                        self.send_header('Location', '/login')
                        self.send_header('Cache-Control', 'no-store')
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                    return
                # Public, non-sensitive local script shared by all three pages.
                if parsed.path in ('/assets/aprs-primary.png', '/assets/aprs-secondary.png', '/assets/aprs-overlays.png'):
                    asset = _ASSET_DIR / 'assets' / parsed.path.rsplit('/', 1)[-1]
                    try:
                        contents = asset.read_bytes()
                    except OSError:
                        self._respond(404, '{"error":"APRS sprite missing"}')
                        return
                    self._respond(200, contents, 'image/png', 'public, max-age=86400')
                    return
                if parsed.path == '/assets/web_locale.js':
                    self._respond(200, LOCALE_JS, 'application/javascript; charset=utf-8', 'public, max-age=3600')
                    return
                if parsed.path in ('/app', '/unified', '/control', '/api/config', '/api/tnc', '/api/archive', '/api/archive/positions', '/api/weather', '/api/heard', '/api/alerts', '/api/tx-scheduler', '/messages', '/api/messages', '/operations', '/api/diagnostics', '/api/journal', '/api/backup', '/api/ports'):
                    if not self._allowed_admin(parsed):
                        self._respond(403, '{"error":"Vyžadován administrátorský odkaz."}')
                        return
                    if parsed.path in ('/app', '/unified'):
                        self._respond(200, UNIFIED_HTML, 'text/html; charset=utf-8')
                    elif parsed.path == '/api/ports':
                        try:
                            from serial.tools import list_ports
                            ports = [{'device': p.device, 'description': p.description or ''}
                                     for p in list_ports.comports()]
                        except ImportError:
                            ports = []
                        self._respond(200, json.dumps({'ports': ports,
                             'selected': operator.config.data['serial']['port']}, ensure_ascii=False))
                    elif parsed.path == '/control':
                        self._respond(200, ADMIN_HTML, 'text/html; charset=utf-8')
                    elif parsed.path == '/operations':
                        self._respond(200, OPERATIONS_HTML, 'text/html; charset=utf-8')
                    elif parsed.path == '/api/tnc':
                        self._respond(200, json.dumps(operator.tnc_snapshot(),ensure_ascii=False))
                    elif parsed.path == '/api/archive':
                        try:
                            args=parse_qs(parsed.query)
                            result={'summary':operator.archive.summary(),
                                'packets':operator.archive.packets(args.get('limit',['100'])[0],
                                                      args.get('source',[''])[0])}
                            self._respond(200,json.dumps(result,ensure_ascii=False))
                        except (ValueError,TypeError) as exc:
                            self._respond(400,json.dumps({'error':str(exc)},ensure_ascii=False))
                    elif parsed.path == '/api/archive/positions':
                        try:
                            args=parse_qs(parsed.query)
                            result={'positions':operator.archive.positions(
                                args.get('source',[''])[0],args.get('limit',['300'])[0])}
                            self._respond(200,json.dumps(result,ensure_ascii=False))
                        except (ValueError,TypeError) as exc:
                            self._respond(400,json.dumps({'error':str(exc)},ensure_ascii=False))
                    elif parsed.path == '/api/weather':
                        try:
                            args=parse_qs(parsed.query)
                            result={'stations':list(operator.latest_weather.values())[-50:],
                                'records':operator.archive.weather_rows(
                                    args.get('source',[''])[0],args.get('limit',['100'])[0])}
                            self._respond(200,json.dumps(result,ensure_ascii=False))
                        except (ValueError,TypeError) as exc:
                            self._respond(400,json.dumps({'error':str(exc)},ensure_ascii=False))
                    elif parsed.path == '/api/heard':
                        try:
                            args=parse_qs(parsed.query)
                            result=operator.heard_snapshot(
                                args.get('minutes',['1440'])[0],
                                args.get('receiver',[''])[0])
                            self._respond(200,json.dumps(result,ensure_ascii=False))
                        except (ValueError,TypeError) as exc:
                            self._respond(400,json.dumps({'error':str(exc)},ensure_ascii=False))
                    elif parsed.path == '/api/alerts':
                        self._respond(200,json.dumps(operator.alerts.snapshot(),ensure_ascii=False))
                    elif parsed.path == '/api/tx-scheduler':
                        self._respond(200,json.dumps(operator.tx_snapshot(),ensure_ascii=False))
                    elif parsed.path == '/api/diagnostics':
                        self._respond(200, json.dumps(operator.diagnostics_snapshot(),ensure_ascii=False))
                    elif parsed.path == '/api/journal':
                        args=parse_qs(parsed.query)
                        self._respond(200, json.dumps(operator.journal_snapshot(args.get('limit',['100'])[0],args.get('category',[''])[0]),ensure_ascii=False))
                    elif parsed.path == '/api/backup':
                        self._respond(200, json.dumps(operator.config_backup(),ensure_ascii=False,indent=2))
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
                if parsed.path == '/api/capabilities':
                    self._respond(200, json.dumps({'admin_enabled': operator is not None}))
                elif parsed.path in ('/', '/map'):
                    self._respond(200, HTML, 'text/html; charset=utf-8')
                elif parsed.path == '/api/state':
                    self._respond(200, json.dumps(state.snapshot(), ensure_ascii=False))
                elif parsed.path == '/metrics':
                    # Prometheus-compatible, read-only counters; viewer/session
                    # authorization is enforced before this branch.
                    snap=state.snapshot()
                    def number(value):
                        try:
                            n=int(value)
                            return str(max(0, n))
                        except (ValueError, TypeError, OverflowError):
                            return '0'
                    lines = [
                        '# HELP ok5tvr_aprs_rx_total Received RF AX.25 frames.',
                        '# TYPE ok5tvr_aprs_rx_total counter',
                        'ok5tvr_aprs_rx_total '+number(snap.get('rx')),
                        '# TYPE ok5tvr_aprs_usb_tx_total counter',
                        'ok5tvr_aprs_usb_tx_total '+number(snap.get('tx_requests')),
                        '# TYPE ok5tvr_aprs_igate_forwarded_total counter',
                        'ok5tvr_aprs_igate_forwarded_total '+number(snap.get('igate_sent')),
                        '# TYPE ok5tvr_aprs_igate_rejected_total counter',
                        'ok5tvr_aprs_igate_rejected_total '+number(snap.get('igate_rejected')),
                        '# TYPE ok5tvr_aprs_digi_tx_total counter',
                        'ok5tvr_aprs_digi_tx_total '+number(snap.get('digi',{}).get('tx_written')),
                        '# TYPE ok5tvr_aprs_stations gauge',
                        'ok5tvr_aprs_stations '+number(snap.get('station_count')),
                        '# TYPE ok5tvr_aprs_stations_with_gps gauge',
                        'ok5tvr_aprs_stations_with_gps '+number(snap.get('position_count')),
                        '',
                    ]
                    self._respond(200, '\n'.join(lines), 'text/plain; version=0.0.4; charset=utf-8')

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
                # Same-origin checks are mandatory for every state-changing request.
                origin = self.headers.get('Origin', '')
                expected = f'http://{self.headers.get("Host", "")}'
                if origin and origin != expected:
                    self._respond(403, '{"error":"Cizi Origin je zakazany."}')
                    return
                if parsed.path == '/api/login':
                    if operator is None or not allow_lan and self.client_address[0] not in ('127.0.0.1', '::1'):
                        self._respond(403, '{"error":"Prihlaseni neni dostupne."}')
                        return
                    if not throttle.allowed(self.client_address[0]):
                        self._respond(429, '{"error":"Prilis mnoho pokusu."}')
                        return
                    if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
                        self._respond(415, '{"error":"Expected JSON"}')
                        return
                    try:
                        size = int(self.headers.get('Content-Length', '0'))
                        if not 0 < size <= 1024:
                            raise ValueError()
                        payload = json.loads(self.rfile.read(size).decode('utf-8'))
                        username, token = payload.get('username'), payload.get('token')
                        valid = (isinstance(username, str) and isinstance(token, str)
                                 and secrets.compare_digest(username, login_name)
                                 and secrets.compare_digest(token, admin_key))
                    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
                        valid = False
                    if not valid:
                        throttle.failure(self.client_address[0])
                        self._respond(401, '{"error":"Neplatne prihlasovaci udaje."}')
                        return
                    throttle.success(self.client_address[0])
                    self._respond(200, '{"ok":true}', cookie=session_auth.cookie(session_auth.issue()))
                    return
                if parsed.path == '/api/logout':
                    if not self._signed_in() or self.headers.get('X-APRS-CSRF') != '1':
                        self._respond(403, '{"error":"Unauthorized"}')
                    else:
                        self._respond(200, '{"ok":true}', cookie=session_auth.clear_cookie())
                    return
                if parsed.path != '/api/control' or operator is None:
                    self._respond(404, '{"error":"Neznámá cesta."}')
                    return
                if not allow_lan and self.client_address[0] not in ('127.0.0.1', '::1'):
                    self._respond(403, '{"error":"LAN je vypnutá."}')
                    return
                # Token must be sent in a non-simple custom header: cross-site
                # forms cannot trigger actions; the server has no CORS support.
                if not ((self._signed_in() and self.headers.get('X-APRS-CSRF') == '1')
                        or secrets.compare_digest(self.headers.get('X-APRS-Admin', ''), admin_key)):
                    self._respond(403, '{"error":"Neplatný administrátorský klíč."}')
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
        return f'http://{host}:{self.port}/app'


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
