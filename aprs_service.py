#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OK5TVR APRS v1.7: headless Windows/Linux KISS receiver, RF->IS iGate and DIGI.

Shared protocol, serial, APRS-IS and digipeater modules are also used by the GUI.
Safe defaults: no automatic RF TX and no APRS-IS forwarding on fresh install.

Usage: python3 aprs_service.py --init
       python3 aprs_service.py --links
       python3 aprs_service.py [--lan] [--config /path/config.json]
"""
from __future__ import annotations
import argparse
import collections
import logging
import queue
import signal
import threading
import time
from pathlib import Path

from aprs_digi import DigiConfig, DigiRepeater
from aprs_messages import MessageManager
from aprs_features import (APRSISClient, MonitorState, encode_ui_packet,
                           encode_kiss_data, igate_tnc2)
from aprs_is_to_rf import SelectiveISGate, server_filter
from aprs_serial import SerialReader
from aprs_tcp import TCPKissReader, TCPKissHub
from aprs_archive import APRSArchive
from aprs_weather import decode_weather
from aprs_station import aprsis_position
from aprs_telemetry import RadioWindow, symbol_code, aprsis_telemetry_lines
from aprs_operations import Journal, backup_document, validate_restore_document, validate_object_request, object_payload
from aprs_messages import normalize_path
from service_config import ServiceConfig, DEFAULT_PATH
from web_panel import WebPanel, local_ipv4

try:
    from serial.tools import list_ports
except ImportError:
    list_ports = None

LOG = logging.getLogger('ok5tvr.aprs')


def find_radio_port(configured='auto'):
    if configured.lower() != 'auto':
        return configured
    if list_ports is None:
        return None
    entries = list(list_ports.comports())
    favored = [p.device for p in entries
               if any(term in ((p.description or '') + ' ' + (p.manufacturer or '')).lower()
                      for term in ('quansheng', 'uv-k1', 'f4hwn', 'py32'))]
    if len(favored) == 1:
        return favored[0]
    # Prefer one CDC-ACM port, not an arbitrary CH340/GPS/serial adapter.
    acm = [p.device for p in entries if 'ttyACM' in p.device or 'usbmodem' in p.device.lower()]
    if len(acm) == 1:
        return acm[0]
    if len(entries) == 1:
        return entries[0].device
    return None  # Ambiguous or absent: ask user to specify an exact port.


class APRSService:
    def __init__(self, config: ServiceConfig, force_lan=False):
        self.config = config
        self.state = MonitorState()
        self.events = queue.Queue(maxsize=10000)
        self.commands = queue.Queue(maxsize=50)
        self.stop = threading.Event()
        self.reader = None
        self.serial_stop = None
        self.session = 0
        self.radio_ready = False
        self.next_serial_attempt = 0.0
        self.last_serial_warning = 0.0
        self.last_manual_tx = float('-inf')
        self.igate_client = None
        self.igate_events = None  # dedicated queue; stale client events cannot overwrite a new session
        self.want_digi = bool(config.data['digi']['autostart'])
        self.gate_cache = {}
        self.isrf = SelectiveISGate(config.data['is_to_rf'], config.data['igate']['call'])
        m = config.data['messages']
        self.messages = MessageManager(config.path.with_name('messages.sqlite3'),
                                      config.data['igate']['call'], m['path'],
                                      m['auto_ack'], m['retry_seconds'], m['max_attempts'],
                                      m.get('receive_aliases', []))
        self.digi = self._make_digi()
        self.state.update_digi(self.digi.snapshot())
        self._update_position()
        self.web = WebPanel(self.state, operator=self,
                            viewer_token=config.secrets['viewer_token'],
                            admin_token=config.secrets['admin_token'])
        self.force_lan = force_lan
        self.stats = collections.Counter()
        self.started_at = time.monotonic()
        self.last_frame_at = None
        self.last_rx_utc = None
        self.last_usb_error = ''
        self.last_igate_error = ''
        self.serial_connections = 0
        self.journal = Journal(config.path.with_name('operations.sqlite3'))
        self.last_object_tx = float('-inf')
        self.object_history = collections.deque(maxlen=40)
        self.telemetry = RadioWindow()
        self.telemetry_seq = {'igate': 0, 'digi': 0}
        self.telemetry_next = time.monotonic() + config.data['telemetry']['interval_minutes'] * 60
        self.telemetry_epoch = -1
        self.telemetry_metadata_at = {}
        self.telemetry_last_sent = {}
        self.last_manual_telemetry = float('-inf')
        self.digi_last_position = float('-inf')  # APRS-IS position
        self.digi_last_rf_position = float('-inf')  # RF KISS position
        self.last_digi_rf_beacon_utc = None  # USB write success, not proof of RF transmission
        self.rf_telemetry_pending = collections.deque(maxlen=8)
        self.rf_telemetry_next_tx = 0.0
        self.next_telemetry_ui = 0.0
        self.running = False
        self.serial_enabled = True  # desktop UI may disconnect without exiting
        self.tcp_hub = None
        self.tnc_tx_permission = False  # network clients NEVER transmit on startup
        self.archive = APRSArchive(config.path.with_name('aprs_history.sqlite3'),
                                    config.data['archive']['retention_days'],
                                    config.data['archive']['max_rows'])
        self.archive.prune()
        self.latest_weather = {}

    def _make_digi(self):
        d = self.config.data['digi']
        return DigiRepeater(DigiConfig(d['call'], d['mode'], d['trace'],
                                       d['delay_s'], d['max_per_min'], d['min_gap_s']))

    def _update_position(self):
        p = self.config.data['position']
        self.state.set_own_position({
            'call': self.config.data['igate']['call'],
            'lat': p['latitude'], 'lon': p['longitude'],
            'beacon': p['beacon_enabled'], 'comment': p['comment'],
            'symbol': symbol_code(self.config.data['igate']['symbol_table'],
                                  self.config.data['igate']['symbol'],
                                  self.config.data['igate']['overlay'])
        } if p['latitude'] is not None else None)

        d=self.config.data['digi']
        self.state.set_digi_position({
            'call':d['call'], 'lat':p['latitude'], 'lon':p['longitude'],
            'active':self.digi.enabled,
            'symbol':symbol_code(d['symbol_table'], d['symbol'], d['overlay'])
        } if p['latitude'] is not None else None)

    def _beacon_line(self):
        p = self.config.data['position']
        if not p['beacon_enabled']:
            return None
        return aprsis_position(self.config.data['igate']['call'], p['latitude'],
                               p['longitude'], p['comment'],
                               symbol_code(self.config.data['igate']['symbol_table'],
                                           self.config.data['igate']['symbol'],
                                           self.config.data['igate']['overlay']))

    # Methods invoked by local web request handlers; perform changes on the
    # service thread. Never directly mutate running RF/IGate state from HTTP.
    def public_config(self):
        result = self.config.public_view()
        return result

    def messages_snapshot(self):
        result = self.messages.snapshot()
        result['default_target'] = self.config.data['messages']['target']
        result['radio_ready'] = self.radio_ready
        result['last_rf_frame_utc'] = self.last_rx_utc
        return result

    def diagnostics_snapshot(self):
        now=time.monotonic()
        return {
            'uptime_s':round(now-self.started_at), 'radio_connected':self.radio_ready,
            'usb_alert': bool(not self.radio_ready and now-self.started_at>45),
            'usb_port':str(self.reader.port) if self.reader else '',
            'tnc_transport':self.config.data['tnc']['transport'],
            'tnc':self.tnc_snapshot(),
            'archive':self.archive.summary(),
            'journal_storage':self.journal.stats(),
            'latest_weather':list(self.latest_weather.values())[-20:],
            'usb_connections':self.serial_connections,
            'last_rf_frame_utc':self.last_rx_utc,
            'seconds_since_rf':None if self.last_frame_at is None else round(now-self.last_frame_at),
            'radio_activity':'USB connected; RF activity not confirmed' if self.radio_ready and self.last_frame_at is None else
                 ('RF packet recently received' if self.last_frame_at is not None and now-self.last_frame_at<300 else 'No recent RF packets (may be normal)'),
            'last_usb_error':self.last_usb_error,
            'igate_connected':bool(self.igate_client and self.igate_client.connected.is_set()),
            'igate_last_error':self.last_igate_error,
            'igate_enabled':self.igate_client is not None,
            'is_to_rf':self.isrf.snapshot(),
            'aprsis_received_lines':self.igate_client.received_lines if self.igate_client else 0,
            'aprsis_rx_dropped':self.igate_client.incoming_dropped if self.igate_client else 0,
            'digi':self.digi.snapshot(),
            'counters':dict(self.stats),
            'recent_objects':list(self.object_history),
            'telemetry': self.telemetry_snapshot(),
            'last_telemetry_utc':dict(self.telemetry_last_sent),
            'last_digi_rf_beacon_utc':self.last_digi_rf_beacon_utc,
        }

    def tnc_snapshot(self):
        conf=self.config.data['tnc']
        hub=self.tcp_hub.snapshot() if self.tcp_hub else {
            'running':False,'host':conf['kiss_server_host'],
            'port':conf['kiss_server_port'],'clients':0,'rx_only':True,
            'frames_published':0,'frames_dropped':0,
            'tx_accepted':0,'tx_rejected':0,'last_error':''}
        return {'transport':conf['transport'], 'connected':self.radio_ready,
                'endpoint':str(self.reader.port) if self.reader else '',
                'reconnect_attempts':self.stats['tnc_reconnect_attempts'],
                'reconnect_count':self.serial_connections,
                'server':hub, 'tx_permission':self.tnc_tx_permission}

    def _hub_tx(self, frame):
        # Called only by an authenticated loopback-bound KISS TCP session,
        # with explicit operator permission; no automatic TX enable on restart.
        if not self.tnc_tx_permission or not self.radio_ready or self.reader is None:
            return False
        return self.reader.send(frame, category='network_manual')

    def _start_tnc_hub(self):
        conf=self.config.data['tnc']
        if self.tcp_hub is not None:
            self.tcp_hub.close()
            self.tcp_hub=None
        if not conf['kiss_server_enabled']:
            return
        # Never auto-enable TX even if the persisted config contains a
        # previously saved affirmative setting.
        self.tnc_tx_permission = False
        hub=TCPKissHub(conf['kiss_server_host'],conf['kiss_server_port'],
                       allow_tx=False, tx_request=self._hub_tx)
        hub.start()
        self.tcp_hub=hub
        self.journal.log('TCP','server-start',detail=f"{hub.host}:{hub.port} read-only")

    def telemetry_snapshot(self):
        m=self.telemetry.snapshot()
        m['igate_enabled'] = self.config.data['igate']['telemetry_enabled']
        m['digi_enabled'] = self.config.data['digi']['telemetry_enabled']
        m['interval_minutes'] = self.config.data['telemetry']['interval_minutes']
        m['digi_beacon_enabled'] = self.config.data['digi']['beacon_enabled']
        m['digi_beacon_transport'] = self.config.data['digi']['beacon_transport']
        m['digi_beacon_rf_path'] = self.config.data['digi']['beacon_rf_path']
        m['last_digi_rf_beacon_utc'] = self.last_digi_rf_beacon_utc
        return m

    def journal_snapshot(self, limit=100, category=''):
        return self.journal.read(limit,category)

    def config_backup(self):
        return backup_document(self.config)

    def command(self, action, payload):
        if not self.running or self.stop.is_set():
            raise TimeoutError('Služba není spuštěna.')
        response = queue.Queue(maxsize=1)
        try:
            self.commands.put((action, payload, response), timeout=1.0)
            ok, result = response.get(timeout=6.0)
        except queue.Full as exc:
            raise TimeoutError('Příliš mnoho požadavků.') from exc
        except queue.Empty as exc:
            raise TimeoutError('Služba neodpovídá.') from exc
        if not ok:
            raise ValueError(str(result))
        return result

    def _commands_tick(self):
        for _ in range(30):
            try:
                action, payload, response = self.commands.get_nowait()
            except queue.Empty:
                break
            try:
                result = self._execute(action, payload)
                response.put_nowait((True, result))
            except (ValueError, TypeError, OSError, RuntimeError) as exc:
                response.put_nowait((False, str(exc)))

    def _execute(self, action, data):
        # HDMI panel toggle does not touch USB, DIGI, iGate, RF, or messages.
        if action == 'isrf_save':
            rules = data.get('rules')
            if not isinstance(rules, dict):
                raise ValueError('IS->RF: expected rules object')
            self.config.update({'is_to_rf':rules})
            self.isrf.configure(self.config.data['is_to_rf'],self.config.data['igate']['call'])
            # Subscription lives in the APRS-IS login. Reconnect deliberately;
            # no automatic Internet->RF activation after a rule change.
            if self.igate_client is not None:
                self._disable_igate()
            self.journal.log('ISRF','rules-changed',detail='Filters saved; IS->RF TX off')
            return 'IS->RF filtry uloženy. Směr IS->RF je vypnutý. Znovu připoj iGate a pak jej výslovně zapni.'
        if action == 'isrf_on':
            if data.get('confirm') is not True:
                raise ValueError('Explicit IS->RF RF transmission confirmation required')
            if not self.radio_ready or self.reader is None or self.igate_client is None or (
                    not self.igate_client.connected.is_set()):
                raise ValueError('First connect the KISS TNC and verified APRS-IS')
            self.isrf.start()
            self.reader.isrf_allowed.set()
            self.journal.log('ISRF','enabled',detail='Runtime-only; transmit limits apply')
            return 'APRS-IS -> RF ZAPNUTO, pouze povolené stanice/objekty a platné bezpečnostní filtry.'
        if action == 'isrf_off':
            self.isrf.stop()
            if self.reader:
                self.reader.isrf_allowed.clear()
            self.journal.log('ISRF','disabled')
            return 'APRS-IS -> RF vypnuto; žádné další pakety se nebudou řadit k odeslání.'
        if action == 'isrf_check':
            line = data.get('line', '')
            if type(line) is not str or len(line) > 400:
                raise ValueError('Test APRS-IS: invalid line')
            return self.isrf.inspect(line)
        if action == 'tnc_server_tx':
            # Enabling requires a real runtime confirmation; never persists
            # across restart or USB disconnect.
            if data.get('enabled') is True:
                if data.get('confirm') is not True:
                    raise ValueError('Explicit confirmation required for KISS TCP RF TX')
                conf=self.config.data['tnc']
                if not (self.tcp_hub and conf['kiss_server_host']=='127.0.0.1'):
                    raise ValueError('TCP KISS RF TX only on local loopback server')
                self.tnc_tx_permission=True
                self.tcp_hub.allow_tx=True
                self.journal.log('TCP','tx-enabled',detail='Loopback local client RF access')
                return 'Local TCP KISS TX enabled for this session'
            if data.get('enabled') is False:
                self.tnc_tx_permission=False
                if self.tcp_hub: self.tcp_hub.allow_tx=False
                self.journal.log('TCP','tx-disabled')
                return 'TCP KISS TX disabled'
            raise ValueError('Expected enabled true/false')
        if action == 'display_set':
            if type(data.get('enabled')) is not bool:
                raise ValueError('HDMI panel requires true/false.')
            self.config.update({'display': {'enabled': data['enabled']}})
            return 'HDMI panel povolen.' if data['enabled'] else 'HDMI panel vypnut.'
        # Native desktop UI uses the same service loop and the same USB port.
        if action == 'serial_disconnect':
            self.serial_enabled = False
            self._disable_digi()  # never retain automatic RF permission after manual disconnect
            self._disconnect_reader()
            self.state.update_status(radio='Odpojeno uživatelem')
            return 'USB KISS odpojeno; automatické připojení pozastaveno.'
        if action in ('serial_connect', 'serial_reconnect'):
            if action == 'serial_reconnect':
                self._disable_digi()
                self._disconnect_reader()
            self.serial_enabled = True
            self.next_serial_attempt = 0.0
            return 'Připojování USB KISS; případně nastav správný COM port.'
        if action == 'telemetry_send_now':
            if data.get('confirm') is not True:
                raise ValueError('APRS telemetry send requires confirmation.')
            if time.monotonic() - self.last_manual_telemetry < 60:
                raise ValueError('Manual APRS telemetry is limited to once per minute.')
            is_online = bool(self.igate_client and self.igate_client.connected.is_set())
            digi_rf = bool(self.config.data['digi']['telemetry_enabled'] and
                           self.config.data['digi']['telemetry_transport'] == 'rf' and
                           self.digi.enabled and self.radio_ready)
            if not is_online and not digi_rf:
                raise ValueError('Enable APRS-IS or an explicitly configured RF DIGI telemetry output first.')
            count = self._telemetry_send(force_metadata=True)
            if count == 0:
                raise ValueError('Enable iGate or DIGI telemetry first.')
            self.last_manual_telemetry = time.monotonic()
            return f'Telemetry packets scheduled/submitted: {count}; route(s) per configured transport. RF requires DIGI active and uses spaced KISS frames.'
        if action == 'restore_config':
            if data.get('confirm') is not True:
                raise ValueError('Obnovení nastavení vyžaduje potvrzení.')
            restored=validate_restore_document(data.get('backup'))
            # Always disable transmit before applying restored settings.
            self._disable_digi()
            self._disable_igate()
            self.messages.usb_closed()
            old_port=self.config.data['serial']['port']
            old_tnc=dict(self.config.data['tnc'])
            self.config.update(restored)
            self.isrf.configure(self.config.data['is_to_rf'], self.config.data['igate']['call'])
            self.messages.configure(self.config.data['igate']['call'],
                    self.config.data['messages']['path'],False,
                    self.config.data['messages']['retry_seconds'],
                    self.config.data['messages']['max_attempts'],
                    self.config.data['messages'].get('receive_aliases', []))
            self._update_position()
            self.telemetry_epoch = -1
            self.rf_telemetry_pending.clear()
            self.digi_last_position = float('-inf')
            self.digi_last_rf_position = float('-inf')
            self.digi=self._make_digi()
            self.state.update_digi(self.digi.snapshot())
            self.tnc_tx_permission=False
            if self.tcp_hub:
                self.tcp_hub.allow_tx=False
            if old_tnc != self.config.data['tnc']:
                self._start_tnc_hub()
            self.archive.retention_days=self.config.data['archive']['retention_days']
            self.archive.max_rows=self.config.data['archive']['max_rows']
            self.archive.prune()
            if old_port!=self.config.data['serial']['port'] or (
                    old_tnc['transport']!=self.config.data['tnc']['transport'] or
                    old_tnc['tcp_host']!=self.config.data['tnc']['tcp_host'] or
                    old_tnc['tcp_port']!=self.config.data['tnc']['tcp_port']):
                self._disconnect_reader()
                self.next_serial_attempt=0
            self.journal.log('CONFIG','restore',detail='Credentials preserved; RF/IS autostart off')
            return 'Konfigurace obnovena. RF/IS autostart a automatické ACK jsou vypnuté; případné další nastavení ověř.'
        if action == 'status_send':
            if data.get('confirm') is not True:
                raise ValueError('RF status vyžaduje potvrzení.')
            if not self.radio_ready or self.reader is None:
                raise ValueError('USB KISS TNC není připojeno.')
            if time.monotonic()-self.last_object_tx<30:
                raise ValueError('Mezi dvěma ručními APRS majáky vyčkej 30 sekund.')
            message=data.get('text','')
            if (not isinstance(message,str) or not 1<=len(message)<=67
                    or any(ord(c)<32 or ord(c)>126 for c in message)):
                raise ValueError('Status: 1–67 tisknutelných ASCII znaků.')
            path=normalize_path(data.get('path','DIRECT'))
            raw=encode_ui_packet(self.config.data['igate']['call'],'APRS',path,'>'+message)
            if not self.reader.send(encode_kiss_data(raw),category='status'):
                raise ValueError('TX fronta obsazená.')
            self.last_object_tx=time.monotonic()
            self.journal.log('STATUS','queued',self.config.data['igate']['call'],detail=message)
            return 'Jednorázový APRS status předán do KISS fronty.'
        if action == 'position_send':
            if data.get('confirm') is not True:
                raise ValueError('RF poziční maják vyžaduje potvrzení.')
            if not self.radio_ready or self.reader is None:
                raise ValueError('USB KISS TNC není připojeno.')
            p=self.config.data['position']
            if p['latitude'] is None or p['longitude'] is None:
                raise ValueError('Nejprve nastav GPS polohu iGate.')
            if time.monotonic()-self.last_object_tx<30:
                raise ValueError('Vyčkej 30 sekund mezi RF objekty/majáky.')
            from aprs_station import aprs_coord
            path=normalize_path(data.get('path','DIRECT'))
            icon=symbol_code(self.config.data['igate']['symbol_table'],
                             self.config.data['igate']['symbol'],
                             self.config.data['igate']['overlay'])
            info='!'+aprs_coord(p['latitude'],True)+icon[0]+aprs_coord(p['longitude'],False)+icon[1]+p['comment']
            raw=encode_ui_packet(self.config.data['igate']['call'],'APRS',path,info)
            if not self.reader.send(encode_kiss_data(raw),category='position'):
                raise ValueError('TX fronta obsazená.')
            self.last_object_tx=time.monotonic()
            self.journal.log('POSITION','queued',self.config.data['igate']['call'],detail=path)
            return 'Ruční RF poloha předána do USB KISS fronty.'
        if action == 'object_send':
            if data.get('confirm') is not True:
                raise ValueError('APRS object TX vyžaduje výslovné potvrzení.')
            if not self.radio_ready or self.reader is None:
                raise ValueError('USB KISS TNC není připojeno.')
            if time.monotonic()-self.last_object_tx<30:
                raise ValueError('Mezi dvěma objektovými TX vyčkej 30 sekund.')
            obj=validate_object_request(data)
            raw=encode_ui_packet(self.config.data['igate']['call'],'APRS',obj['path'],
                   object_payload(obj['name'],obj['lat'],obj['lon'],obj['comment'],
                                  obj['alive'],obj['symbol_table'],obj['symbol']))
            if not self.reader.send(encode_kiss_data(raw),category='object'):
                raise ValueError('TX fronta obsazená.')
            self.last_object_tx=time.monotonic()
            item={'name':obj['name'],'alive':obj['alive'],'lat':obj['lat'],'lon':obj['lon'],
                  'path':obj['path'],'queued_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
            self.object_history.appendleft(item)
            self.journal.log('OBJECT','queued',self.config.data['igate']['call'],obj['name'],
                             ('live' if obj['alive'] else 'kill')+' '+obj['path'])
            return 'APRS objekt předán do USB KISS TX fronty; fyzické RF vysílání ověř druhým přijímačem.'
        if action == 'save':
            changes = data.get('config', {})
            if not isinstance(changes, dict):
                raise ValueError('Nastavení musí být objekt.')
            if any(not isinstance(changes.get(section, {}), dict) for section in ('digi','messages')):
                raise ValueError('Nastavení DIGI a zpráv musí být objekt.')
            updated_digi = changes.get('digi', {})
            requested_digi_autostart = updated_digi.get('autostart', False)
            rf_beacon_enabled = (updated_digi.get('beacon_enabled',self.config.data['digi']['beacon_enabled']) and
                                 updated_digi.get('beacon_transport',self.config.data['digi']['beacon_transport']) == 'rf')
            if rf_beacon_enabled and any(field in updated_digi for field in
                                         ('beacon_enabled','beacon_transport','beacon_rf_path')) and \
                    data.get('confirm_rf_beacon') is not True:
                raise ValueError('Automatic DIGI RF position beacon requires explicit confirmation.')
            rf_telem_enabled = (updated_digi.get('telemetry_enabled',self.config.data['digi']['telemetry_enabled']) and
                                updated_digi.get('telemetry_transport',self.config.data['digi']['telemetry_transport']) == 'rf')
            if rf_telem_enabled and data.get('confirm_rf_telemetry') is not True:
                raise ValueError('Automatic DIGI RF telemetry requires explicit confirmation.')
            if requested_digi_autostart and data.get('confirm_auto_tx') is not True:
                raise ValueError('Automatický RF TX po startu vyžaduje výslovné potvrzení.')
            if changes.get('messages', {}).get('auto_ack') is True and data.get('confirm_auto_ack') is not True:
                raise ValueError('Zapnutí automatických RF ACK vyžaduje výslovné potvrzení.')
            passcode = data.get('passcode')
            if passcode is not None and not isinstance(passcode, str):
                raise ValueError('Neplatný APRS-IS passcode.')
            previous_port = self.config.data['serial']['port']
            previous_tnc = dict(self.config.data['tnc'])
            previous_archive = dict(self.config.data['archive'])
            previous_call = self.config.data['igate']['call']
            previous_messages = dict(self.config.data['messages'])
            self.config.update(changes, passcode=passcode)
            self.isrf.configure(self.config.data['is_to_rf'], self.config.data['igate']['call'])
            if previous_call != self.config.data['igate']['call'] or previous_messages != self.config.data['messages']:
                # Persisted pending transmissions are invalid when callsign/path changes.
                self.messages.usb_closed()
            m = self.config.data['messages']
            self.messages.configure(self.config.data['igate']['call'], m['path'], m['auto_ack'],
                                    m['retry_seconds'], m['max_attempts'], m.get('receive_aliases', []))
            self._update_position()
            self.telemetry_epoch = -1
            self.telemetry_next = time.monotonic() + self.config.data['telemetry']['interval_minutes'] * 60
            self.telemetry_metadata_at.clear()
            self.rf_telemetry_pending.clear()
            self.digi_last_position = float('-inf')
            self.digi_last_rf_position = float('-inf')
            # No silent change to an already-running RF DIGI configuration.
            if self.want_digi:
                self._disable_digi()
            self.digi = self._make_digi()
            self.state.update_digi(self.digi.snapshot())
            if self.igate_client:
                self._disable_igate()
            if (previous_port != self.config.data['serial']['port'] or
                    previous_tnc['transport'] != self.config.data['tnc']['transport'] or
                    previous_tnc['tcp_host'] != self.config.data['tnc']['tcp_host'] or
                    previous_tnc['tcp_port'] != self.config.data['tnc']['tcp_port']):
                self._disconnect_reader()
                self.next_serial_attempt = 0.0
            if previous_tnc != self.config.data['tnc']:
                self.tnc_tx_permission=False
                if self.tcp_hub:
                    self.tcp_hub.allow_tx=False
                self._start_tnc_hub()
            if previous_archive != self.config.data['archive']:
                self.archive.retention_days=self.config.data['archive']['retention_days']
                self.archive.max_rows=self.config.data['archive']['max_rows']
                self.archive.prune()
            LOG.info('Konfigurace uložena; provozní změny RF/IS vyžadují nové zapnutí.')
            return 'Nastavení uloženo. Po úpravě aktivní iGate/DIGI znovu zapni. Změnu web portu/LAN proveď restartem služby.'

        if action == 'igate_on':
            if data.get('confirm') is not True:
                raise ValueError('Povol odesílání do APRS-IS výslovně.')
            self._start_igate()
            return 'APRS-IS iGate spouštěna (RF → internet, bez IS → RF).'
        if action == 'igate_off':
            self._disable_igate()
            return 'APRS-IS iGate vypnutá.'
        if action == 'digi_on':
            if data.get('confirm') is not True:
                raise ValueError('Potvrď povolení RF retransmisí.')
            if not self.radio_ready or not self.reader:
                raise ValueError('Nejdřív připoj aktivní USB KISS TNC.')
            self.want_digi = True
            self._enable_digi()
            return 'DIGI povoleno. Na UV-K1 musí být KISS TX a interní DIGI vypnutá.'
        if action == 'digi_off':
            self._disable_digi()
            return 'DIGI vypnuto; čekající retransmise zrušeny.'
        if action == 'message_send':
            if data.get('confirm') is not True:
                raise ValueError('Potvrď jednotlivé RF odeslání a případná automatická opakování.')
            if not self.radio_ready or self.reader is None:
                raise ValueError('USB KISS TNC není připojeno nebo nemá povolený TX.')
            # Sending is RF-only; iGate forwarding of the RF packet is independent.
            return self.messages.compose(data.get('target'), data.get('text'), data.get('path'))
        if action == 'message_cancel':
            return self.messages.cancel(data.get('id'))
        if action in ('message_ack', 'message_rej'):
            if data.get('confirm') is not True:
                raise ValueError('Potvrď jednorázové odeslání ACK přes RF.')
            if not self.radio_ready or not self.reader:
                raise ValueError('USB KISS TNC není připojeno.')
            return self.messages.acknowledge_manual(data.get('id'), reject=(action == 'message_rej'))
        if action == 'tx_test':
            if data.get('confirm') is not True:
                raise ValueError('RF TX vyžaduje výslovné potvrzení.')
            if not self.radio_ready or not self.reader:
                raise ValueError('USB KISS TNC není připojeno.')
            if time.monotonic() - self.last_manual_tx < 30:
                raise ValueError('Mezi testy TX vyčkej alespoň 30 sekund.')
            call = self.config.data['igate']['call']
            raw = encode_ui_packet(call, 'APRS', '', '>OK5TVR APRS KISS v1.7 test')
            if not self.reader.send(encode_kiss_data(raw), category='manual'):
                raise ValueError('TX fronta je obsazená. Zkus to později.')
            self.last_manual_tx = time.monotonic()
            return 'Jednorázový APRS status předán do USB KISS fronty (skutečné RF ověř druhým přijímačem).'
        raise ValueError('Nepodporovaný příkaz.')

    def _start_igate(self):
        if self.igate_client is not None:
            return
        if not self.config.secrets['igate_passcode']:
            raise ValueError('Nejprve ulož APRS-IS passcode v nastavení.')
        i = self.config.data['igate']
        own_events = queue.Queue(maxsize=500)
        client = APRSISClient(i['call'], self.config.secrets['igate_passcode'],
                            i['host'], i['port'], own_events,
                            subscription=server_filter(self.config.data['is_to_rf']))
        client.configure_position(self._beacon_line(),
                                  self.config.data['position']['beacon_interval'])
        self.igate_client = client
        self.igate_events = own_events
        self.state.update_status(igate='Připojuji k APRS-IS')
        client.start()
        LOG.info('Spuštěna iGate RF->APRS-IS %s (%s:%s)', i['call'], i['host'], i['port'])

    def _disable_igate(self):
        self.isrf.stop()
        if self.reader:
            self.reader.isrf_allowed.clear()
        old = self.igate_client
        self.igate_client = None
        self.igate_events = None
        if old:
            old.stop.set()
            old.join(timeout=2.5)
        self.telemetry_epoch = -1
        self.state.update_status(igate='Vypnuto')

    def _enable_digi(self):
        if not self.radio_ready or self.reader is None:
            return
        self.digi.start()
        self.reader.digi_allowed.set()
        self.state.update_digi(self.digi.snapshot())
        self.digi_last_position=float('-inf')
        self.digi_last_rf_position=float('-inf')
        self._update_position()
        LOG.warning('RF DIGI ZAPNUTO: %s %s', self.digi.config.call, self.digi.config.mode)

    def _disable_digi(self):
        self.want_digi = False
        self.rf_telemetry_pending.clear()
        if self.reader:
            self.reader.digi_allowed.clear()
        self.digi.stop()
        self.state.update_digi(self.digi.snapshot())
        self._update_position()

    def _disconnect_reader(self):
        self.isrf.stop()  # revoke Internet-to-RF gate after any KISS outage
        if self.reader:
            self.reader.isrf_allowed.clear()
        # A dropped USB/TCP link revokes previously granted RF permissions.
        # The operator must explicitly enable DIGI/network TX again.
        self.want_digi = False
        self.tnc_tx_permission=False
        if self.tcp_hub:
            self.tcp_hub.allow_tx=False
        if self.reader is not None:
            previous = self.reader
            previous.digi_allowed.clear()
            if self.serial_stop:
                self.serial_stop.set()
            previous.join(timeout=1.0)
            self.reader = None
        self.radio_ready = False
        self.rf_telemetry_pending.clear()
        self.messages.usb_closed()
        self.digi.stop()
        self.state.update_digi(self.digi.snapshot())
        self._update_position()
        self.state.update_status(radio='Odpojeno')

    def _connect_tick(self):
        if not self.serial_enabled:
            return
        if self.reader is not None or time.monotonic() < self.next_serial_attempt:
            return
        conf=self.config.data['tnc']
        port = (f"{conf['tcp_host']}:{conf['tcp_port']}" if conf['transport']=='tcp'
                else find_radio_port(self.config.data['serial']['port']))
        self.next_serial_attempt = time.monotonic() + self.config.data['serial']['retry_seconds']
        if port is None:
            self.state.update_status(radio='USB nenalezeno / více portů; nastav port')
            if time.monotonic() - self.last_serial_warning > 45:
                self.journal.log('USB','missing',detail='Port not found or ambiguous')
                LOG.warning('USB KISS port nenalezen/nejednoznačný; zvol /dev/ttyACM0 nebo COMx.')
                self.last_serial_warning = time.monotonic()
            return
        self.session += 1
        self.stats['tnc_reconnect_attempts']+=1
        self.serial_stop = threading.Event()
        if conf['transport']=='tcp':
            self.reader=TCPKissReader(conf['tcp_host'],conf['tcp_port'],self.events,
                                      self.serial_stop,self.session)
        else:
            self.reader=SerialReader(port,self.config.data['serial']['baud'],self.events,
                                     self.serial_stop,self.session)
        self.radio_ready = False
        self.state.update_status(radio=f'Připojuji {port}...')
        self.reader.start()

    def _handle_events(self):
        for _ in range(250):
            try:
                session, event, value = self.events.get_nowait()
            except queue.Empty:
                break
            if session not in (self.session, -1):
                continue
            if session == -1:
                continue  # old GUI-style events; headless APRS-IS has its own queue
            if event == 'connected':
                self.radio_ready = True
                self.serial_connections += 1
                self.last_usb_error=''
                self.journal.log('USB','connected',detail=str(value))
                self.state.update_status(radio='Připojeno '+str(value))
                LOG.info('USB KISS připojeno: %s', value)
                if self.want_digi:
                    self._enable_digi()
            elif event == 'frame':
                self._on_frame(value)
            elif event == 'tx_written':
                self.journal.log('TX','written',detail=str(value))
                self.stats['tx_written']+=1
                self.state.note_tx()
                if isinstance(value, dict):
                    category=value.get('category','unknown')
                    self.telemetry.record_tx(category)
                    if category == 'igate_is_to_rf':
                        self.stats['isrf_usb_written'] += 1
                        self.journal.log('ISRF','usb-written',
                            detail='USB KISS write successful; RF transmission unverified')
                    if category == 'telemetry_rf':
                        self.journal.log('TELEM','rf-usb-written',self.config.data['digi']['call'])
                    if category == 'digi_beacon_rf':
                        self.last_digi_rf_beacon_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
                        self.stats['digi_beacon_rf_written'] += 1
                        self.journal.log('BEACON','rf-usb-written',self.config.data['digi']['call'])
                if isinstance(value, dict) and value.get('category', '').startswith(('msg:', 'msgack:')):
                    self.messages.tx_written(value['category'])
                if isinstance(value, dict) and value.get('category') == 'digi':
                    self.digi.mark_written()
                    self.state.update_digi(self.digi.snapshot())
            elif event == 'tx_error':
                self.journal.log('TX','error',detail=str(value))
                self.stats['tx_error']+=1
                self.telemetry.record_tx_error()
                LOG.warning('TX USB selhal: %s', value)
                if isinstance(value, dict) and value.get('category', '').startswith(('msg:', 'msgack:')):
                    self.messages.tx_error(value['category'], value.get('error', 'Chyba USB'))
                if isinstance(value, dict) and value.get('category') == 'digi':
                    self.digi.mark_error()
                    self.state.update_digi(self.digi.snapshot())
            elif event == 'invalid':
                self.journal.log('KISS','invalid',detail=str(value))
                self.stats['invalid'] += 1
            elif event == 'error':
                self.last_usb_error=str(value)
                self.journal.log('USB','error',detail=str(value))
                LOG.warning('Chyba USB KISS: %s', value)
                self.state.update_status(radio='Chyba USB: '+str(value)[:95])
            elif event == 'closed':
                self.journal.log('USB','disconnected')
                self.stats['usb_disconnects']+=1
                self._disconnect_reader()
                LOG.info('USB odpojeno, automatický pokus o opětovné připojení.')
        # Only consume events from the current APRS-IS session. A disconnected
        # client cannot overwrite the new session's status or counters.
        if self.igate_events is not None:
            for _ in range(120):
                try:
                    _, event, value = self.igate_events.get_nowait()
                except queue.Empty:
                    break
                if event == 'igate_status':
                    self.state.update_status(igate=value)
                    if str(value).startswith(('Odpojeno', 'Vypnuto')):
                        self.isrf.stop()
                        if self.reader:
                            self.reader.isrf_allowed.clear()
                elif event == 'igate_received':
                    # Parse all incoming APRS-IS packets on the service thread,
                    # never on the socket thread; only explicitly selected
                    # sources can reach the existing single-slot KISS TX queue.
                    ready = bool(self.radio_ready and self.reader is not None)
                    is_online = bool(self.igate_client and
                                     self.igate_client.connected.is_set())
                    accepted,reason = self.isrf.process(
                        value,
                        send=(lambda frame:self.reader.send(
                            frame,category='igate_is_to_rf')) if ready else None,
                        rf_ready=ready, is_ready=is_online)
                    self.stats['isrf_'+reason] += 1
                    if accepted:
                        self.journal.log('ISRF','rf-queued',
                            detail='APRS-IS selected packet queued for USB KISS')
                elif event == 'igate_sent':
                    self.journal.log('IGATE','sent',detail=str(value))
                    self.stats['igate_sent']+=1
                    self.state.note_igate(True)
                    self.telemetry.record_gate()
                elif event == 'igate_local_sent':
                    kind = value.get('kind', 'unknown') if isinstance(value,dict) else 'unknown'
                    self.stats['aprsis_local_'+kind] += 1
                    if kind == 'digi_beacon':
                        self.journal.log('BEACON','sent',self.config.data['digi']['call'],detail='APRS-IS DIGI position')
                    elif kind == 'telemetry':
                        self.journal.log('TELEM','sent',detail='APRS-IS local telemetry')
                elif event == 'igate_beacon':
                    self.state.note_beacon()
                elif event == 'igate_error':
                    self.last_igate_error=str(value)
                    self.journal.log('IGATE','error',detail=str(value))
                    self.state.update_status(igate='Chyba: '+str(value)[:120])
                    LOG.warning('APRS-IS: %s', value)

    def _on_frame(self, packet):
        self.last_frame_at=time.monotonic()
        self.last_rx_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        self.stats['rx']+=1
        self.isrf.note_rf(packet)
        loc=self.config.data['position']
        own=(loc['latitude'],loc['longitude']) if loc['latitude'] is not None else None
        if not packet.simulated and packet.source != '?':
            self.telemetry.record_rx(packet.source, packet.latitude, packet.longitude,
                                     own_position=own,position_label=packet.position_label)
        wx=decode_weather(packet.raw_info)
        try:
            self.archive.add(packet, wx)
        except (OSError, ValueError) as exc:
            self.stats['archive_errors']+=1
            if self.stats['archive_errors']==1 or self.stats['archive_errors']%100==0:
                LOG.warning('APRS archive failed (%d events): %s',
                            self.stats['archive_errors'], exc)
        if wx:
            self.latest_weather[packet.source]={'source':packet.source,
                'received_at':self.last_rx_utc,**wx}
            if len(self.latest_weather)>100:
                oldest=next(iter(self.latest_weather))
                self.latest_weather.pop(oldest,None)
        if self.tcp_hub and packet.raw_ax25 and not packet.simulated and packet.source!='?':
            self.tcp_hub.publish(packet.raw_ax25)
        self.journal.log('RX','accepted',packet.source,packet.destination,
                         (packet.raw_info.decode('latin-1','replace') if isinstance(packet.raw_info,bytes) else str(packet.raw_info))[:250])
        msg = self.messages.receive(packet, self.radio_ready)
        if msg:
            LOG.info('APRS zpráva: %s od %s', msg.get('kind'), msg.get('from'))
        if self.digi.enabled and packet.raw_ax25:
            reason=self.digi.receive(packet.raw_ax25)
            self.journal.log('DIGI','checked',packet.source,packet.destination,reason)
            self.state.update_digi(self.digi.snapshot())
        self.state.add(packet)
        if self.igate_client and self.igate_client.connected.is_set():
            line, reason = igate_tnc2(packet, self.igate_client.call)
            if not line:
                self.journal.log('IGATE','rejected',packet.source,packet.destination,reason)
            if line:
                now = time.monotonic()
                key = (packet.source, packet.destination, packet.raw_info)
                if now - self.gate_cache.get(key, float('-inf')) > 30:
                    if self.igate_client.enqueue(line):
                        self.journal.log('IGATE','queued',packet.source,packet.destination)
                        self.gate_cache[key] = now
                    else:
                        self.state.note_igate(False)
                        self.journal.log('IGATE','queue-full',packet.source,packet.destination)
                if len(self.gate_cache) > 4000:
                    self.gate_cache = {key:stamp for key,stamp in self.gate_cache.items() if now-stamp < 60}
        if self.state.rx % 50 == 0:
            LOG.info('APRS RF RX: %s platných rámců', self.state.rx)

    def _messages_tick(self):
        self.messages.tx_tick(self.reader, self.radio_ready)

    def _digi_tick(self):
        if not self.digi.enabled or not self.radio_ready or self.reader is None:
            return
        p = self.digi.ready()
        if p is None:
            return
        if self.reader.send(encode_kiss_data(p.raw), category='digi'):
            self.journal.log('DIGI','queued',detail=p.input_path)
            self.digi.mark_queued(p.signature)
            self.state.update_digi(self.digi.snapshot())

    def _telemetry_flags(self):
        m=self.telemetry.snapshot()
        p=self.config.data['position']
        return dict(usb=self.radio_ready,
                    aprsis=bool(self.igate_client and self.igate_client.connected.is_set()),
                    digi=self.digi.enabled, heard=m['rx_packets']>0,
                    tx_error=m['tx_errors']>0, gps=p['latitude'] is not None,
                    telemetry=True, reserved=False)

    def _telemetry_send(self, force_metadata=False):
        client=self.igate_client
        is_online=bool(client and client.connected.is_set())
        now=time.monotonic()
        metrics=self.telemetry.snapshot()
        flags=self._telemetry_flags()
        total=0
        for role in ('igate','digi'):
            opts=self.config.data[role]
            if not opts['telemetry_enabled']:
                continue
            if role == 'digi' and (not self.digi.enabled or not self.radio_ready):
                continue
            rf = role == 'digi' and opts['telemetry_transport'] == 'rf'
            if rf:
                if self.rf_telemetry_pending or not self.reader:
                    continue  # no overlapping RF metadata / telemetry bursts
            elif not is_online:
                continue
            call=opts['call']
            meta_due=(force_metadata or now-self.telemetry_metadata_at.get(role,float('-inf'))>=6*3600)
            seq=self.telemetry_seq[role]
            packets=aprsis_telemetry_lines(call,seq,metrics,role,flags,metadata=meta_due)
            if rf:
                # Only a local KISS radio transmits. Deliberately paced below
                # one frame per 12s to avoid metadata bursts on 144.800 MHz.
                from aprs_features import encode_ui_packet, encode_kiss_data
                for line in packets:
                    info=line.split('TCPIP*:',1)[1]
                    raw=encode_ui_packet(call,'APRS',opts['telemetry_rf_path'],info)
                    self.rf_telemetry_pending.append(encode_kiss_data(raw))
                    total+=1
                self.rf_telemetry_next_tx=max(self.rf_telemetry_next_tx,now)
                self.journal.log('TELEM','rf-scheduled',call,detail=f'{total} frames / path {opts["telemetry_rf_path"] or "DIRECT"}')
            else:
                for line in packets:
                    if not client.enqueue_local(line,'telemetry'):
                        return total  # preserve sequence; no queue flooding on failures
                    total+=1
            if meta_due:
                self.telemetry_metadata_at[role]=now
            self.telemetry_seq[role]=(seq+1)%1000
            self.telemetry_last_sent[role]=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        return total

    def _rf_telemetry_tick(self):
        if not self.rf_telemetry_pending or not self.digi.enabled or not self.radio_ready or self.reader is None:
            return
        now=time.monotonic()
        if now < self.rf_telemetry_next_tx:
            return
        frame=self.rf_telemetry_pending[0]
        if self.reader.send(frame, category='telemetry_rf'):
            self.rf_telemetry_pending.popleft()
            self.rf_telemetry_next_tx=now+12

    def _rf_digi_beacon_tick(self):
        """Queue a DIGI position via KISS on start and every configured interval.

        This is deliberately separate from APRS-IS beacons. DIGI RF TX must
        already have been explicitly enabled; a KISS write does not prove RF.
        """
        d=self.config.data['digi']
        p=self.config.data['position']
        if (not d['beacon_enabled'] or d['beacon_transport'] != 'rf' or
                not self.digi.enabled or not self.radio_ready or self.reader is None or
                p['latitude'] is None or p['longitude'] is None):
            return
        now=time.monotonic()
        if now-self.digi_last_rf_position < d['beacon_interval']*60:
            return
        if self.rf_telemetry_pending or now < self.rf_telemetry_next_tx:
            return  # Keep 12s spacing; no interleaving with T# metadata.
        symbol=symbol_code(d['symbol_table'],d['symbol'],d['overlay'])
        line=aprsis_position(d['call'],p['latitude'],p['longitude'],d['beacon_comment'],symbol)
        # Only the APRS information field belongs in an RF AX.25 UI frame;
        # APRS-IS TCPIP* headers and q constructs must NEVER be put on RF.
        info=line.split(':',1)[1]
        raw=encode_ui_packet(d['call'],'APRS',d['beacon_rf_path'],info)
        if self.reader.send(encode_kiss_data(raw),category='digi_beacon_rf'):
            self.digi_last_rf_position=now
            self.rf_telemetry_next_tx=max(self.rf_telemetry_next_tx,now+12)
            self.journal.log('BEACON','rf-queued',d['call'],
                             detail=d['beacon_rf_path'] or 'DIRECT')

    def _telemetry_tick(self):
        now=time.monotonic()
        if now >= self.next_telemetry_ui:
            self.state.set_telemetry(self.telemetry_snapshot())
            self.next_telemetry_ui = now + 2
        self._rf_telemetry_tick()
        self._rf_digi_beacon_tick()
        now=time.monotonic()
        if now >= self.telemetry_next:
            self._telemetry_send()
            self.telemetry_next=now+self.config.data['telemetry']['interval_minutes']*60
        client=self.igate_client
        if client is None or not client.connected.is_set():
            return
        # On reconnect resend parameter metadata, but not the T# report early.
        epoch=getattr(client,'connection_epoch',0)
        if epoch != self.telemetry_epoch:
            self.telemetry_epoch=epoch
            self.telemetry_metadata_at.clear()
            self.digi_last_position=float('-inf')
        d=self.config.data['digi'];p=self.config.data['position']
        if (d['beacon_enabled'] and d['beacon_transport'] == 'is' and
            self.digi.enabled and self.radio_ready and
            p['latitude'] is not None and now-self.digi_last_position >= d['beacon_interval']*60):
            line=aprsis_position(d['call'],p['latitude'],p['longitude'],
                   d['beacon_comment'], symbol_code(d['symbol_table'],d['symbol'],d['overlay']))
            if client.enqueue_local(line,'digi_beacon'):
                self.digi_last_position=now

    def run(self, with_web=True):
        # One backend, two mutually exclusive frontends: native desktop (no HTTP)
        # and headless Raspberry Pi / browser service. Never open two USB readers.
        c = self.config.data
        self._start_tnc_hub()
        if with_web:
            lan = c['web']['lan'] or self.force_lan
            self.web.start(lan=lan, port=c['web']['port'], fallback=False)
            LOG.info('Web %s:%d (správa jen pomocí soukromého odkazu).',
                     'LAN' if lan else 'localhost', self.web.port)
        else:
            LOG.info('Nativní Windows režim: webový server se nespouští.')
        self.running = True
        if c['igate']['autostart']:
            try:
                self._start_igate()
            except ValueError as exc:
                LOG.warning('iGate nelze automaticky spustit: %s', exc)
        if self.want_digi:
            LOG.warning('V konfiguraci je VÝSLOVNĚ povolen automatický DIGI po připojení USB (RF TX).')
        try:
            while not self.stop.is_set():
                self._commands_tick()
                self._handle_events()
                self._connect_tick()
                self._messages_tick()
                self._digi_tick()
                self._telemetry_tick()
                self.stop.wait(0.08)
        finally:
            self.running = False
            self._disconnect_reader()
            self._disable_igate()
            self.web.close()
            if self.tcp_hub:
                self.tcp_hub.close()
                self.tcp_hub=None
            self.tnc_tx_permission=False
            # Always close all resources even if a full/missing SD card prevents
            # one of the two SQLite queues from draining at shutdown.
            for name, resource in (('APRS archive', self.archive),
                                   ('APRS messages', self.messages),
                                   ('APRS operations journal', self.journal)):
                try:
                    resource.close()
                except Exception:
                    LOG.exception('%s: shutdown/flush failed; check SQLite storage', name)
            LOG.info('Služba OK5TVR zastavena.')


def main():
    parser = argparse.ArgumentParser(description='OK5TVR APRS USB KISS iGate/DIGI bez displeje')
    parser.add_argument('--config', default=str(DEFAULT_PATH), help='Cesta k config.json')
    parser.add_argument('--init', action='store_true', help='Vytvořit konfiguraci a bezpečné přístupové tokeny')
    parser.add_argument('--links', action='store_true', help='Zobrazit URL mapy a správy (uchovej v soukromí)')
    parser.add_argument('--lan', action='store_true', help='Povolit LAN pro toto spuštění (bez změny konfigurace)')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING'])
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level),
                        format='%(asctime)s [%(levelname)s] %(message)s')
    conf = ServiceConfig(args.config).load_or_create()
    if args.init:
        print('Konfigurace:', conf.path)
        print('Tajné údaje:', conf.secret_path)
        print('Ve výchozím stavu iGate i RF DIGI nevysílají.')
        print('Zobrazení soukromých odkazů: python3 aprs_service.py --links')
        return
    if args.links:
        host = local_ipv4() if conf.data['web']['lan'] or args.lan else '127.0.0.1'
        for name, url in conf.links(host).items():
            print(f'{name}: {url}')
        print('Uživatelské jméno:', conf.secrets['web_username'])
        print('Přístupový token:', conf.secrets['admin_token'])
        print('Tyto údaje jsou citlivé. Ukládej je bezpečně, nezveřejňuj a nepoužívej přímý HTTP přístup z internetu.')
        return
    service = APRSService(conf, force_lan=args.lan)
    def halt(*_):
        service.stop.set()
    signal.signal(signal.SIGINT, halt)
    signal.signal(signal.SIGTERM, halt)
    service.run()


if __name__ == '__main__':
    main()
