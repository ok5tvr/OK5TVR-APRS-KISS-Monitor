#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OK5TVR APRS v1.6: headless Windows/Linux KISS receiver, RF->IS iGate and DIGI.

Shared protocol, serial, APRS-IS and digipeater modules are also used by the GUI.
Safe defaults: no automatic RF TX and no APRS-IS forwarding on fresh install.

Usage: python3 aprs_service.py --init
       python3 aprs_service.py --links
       python3 aprs_service.py [--lan] [--config /path/config.json]
"""
from __future__ import annotations
import argparse
import collections
from datetime import datetime, timezone
import logging
import queue
import signal
import threading
import time
from pathlib import Path

from aprs_digi import DigiConfig, DigiRepeater
from aprs_messages import MessageManager
from aprs_operations import (validate_object, object_info, status_info, position_info, make_rf_frame, MAX_OBJECTS)
from aprs_journal import OperationsJournal
from aprs_features import (APRSISClient, MonitorState, encode_ui_packet,
                           encode_kiss_data, igate_tnc2)
from aprs_serial import SerialReader
from aprs_station import aprsis_position
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
        m = config.data['messages']
        self.messages = MessageManager(config.path.with_name('messages.sqlite3'),
                                      config.data['igate']['call'], m['path'],
                                      m['auto_ack'], m['retry_seconds'], m['max_attempts'])
        self.digi = self._make_digi()
        self.state.update_digi(self.digi.snapshot())
        self._update_position()
        self.web = WebPanel(self.state, operator=self,
                            viewer_token=config.secrets['viewer_token'],
                            admin_token=config.secrets['admin_token'])
        self.force_lan = force_lan
        self.stats = collections.Counter()
        self.journal = OperationsJournal(config.path.with_name('events.sqlite3'))
        self.started_monotonic = time.monotonic()
        self.usb_connected_at = None
        self.usb_disconnected_at = self.started_monotonic
        self.last_valid_rx_at = None
        self.last_valid_rx_utc = None
        self.last_usb_error = ''
        self.usb_connect_count = 0
        self._last_health_alert = None
        self.object_schedule_enabled = False  # never auto-start scheduled RF after a reboot
        self.object_next_due = {}
        self.last_object_tx = float('-inf')
        self._journal('SYSTEM', 'SERVICE', detail='APRS headless service initialized', outcome='RX only')
        self.running = False

    def _make_digi(self):
        d = self.config.data['digi']
        return DigiRepeater(DigiConfig(d['call'], d['mode'], d['trace'],
                                       d['delay_s'], d['max_per_min'], d['min_gap_s']))

    def _update_position(self):
        p = self.config.data['position']
        self.state.set_own_position({
            'call': self.config.data['igate']['call'],
            'lat': p['latitude'], 'lon': p['longitude'],
            'beacon': p['beacon_enabled'], 'comment': p['comment']
        } if p['latitude'] is not None else None)

    def _beacon_line(self):
        p = self.config.data['position']
        if not p['beacon_enabled']:
            return None
        return aprsis_position(self.config.data['igate']['call'], p['latitude'],
                               p['longitude'], p['comment'], 'R&')

    # Methods invoked by local web request handlers; perform changes on the
    # service thread. Never directly mutate running RF/IGate state from HTTP.
    def public_config(self):
        result = self.config.public_view()
        result['viewer_token'] = self.config.secrets['viewer_token']
        return result

    def messages_snapshot(self):
        result = self.messages.snapshot()
        result['default_target'] = self.config.data['messages']['target']
        result['radio_ready'] = self.radio_ready
        return result

    def _journal(self, direction, subsystem, source='', destination='', path='', detail='', outcome=''):
        try:
            self.journal.add(direction, subsystem, source, destination, path, detail, outcome)
        except Exception as exc:
            LOG.error('Provozní deník: %s', exc)

    def diagnostics_snapshot(self):
        now = time.monotonic()
        idle = (now - self.last_valid_rx_at if self.last_valid_rx_at is not None
                else (now - self.usb_connected_at if self.usb_connected_at is not None else None))
        h = self.config.data['health']
        age = round(idle, 1) if idle is not None else None
        if not self.radio_ready:
            health = 'disconnected'
        elif idle is not None and idle >= h['quiet_warning_minutes'] * 60:
            health = 'quiet'  # traffic silence is not proof of broken radio firmware
        else:
            health = 'connected_unverified'
        return {'health': health, 'usb_connected': self.radio_ready,
                'radio_activity_confirmed': self.last_valid_rx_at is not None,
                'last_rx_utc': self.last_valid_rx_utc, 'seconds_without_aprs': age,
                'reconnects': max(0, self.usb_connect_count - 1),
                'port': self.reader.port if self.reader else self.config.data['serial']['port'],
                'last_usb_error': self.last_usb_error,
                'next_retry_seconds': max(0, round(self.next_serial_attempt - now)) if not self.radio_ready else 0,
                'aprsis_connected': bool(self.igate_client and self.igate_client.connected.is_set()),
                'aprsis_status': self.state.igate_status,
                'digi': self.digi.snapshot(),
                'messages_pending': self.messages.snapshot()['stats']['pending'],
                'object_schedule_enabled': self.object_schedule_enabled,
                'objects_saved': len(self.config.data['objects']['entries']),
                'log_entries': self.journal.count(), 'uptime_seconds': round(now - self.started_monotonic),
                'counters': dict(self.stats),
                'warning': ('USB KISS odpojeno; probíhá opakované připojování.' if health == 'disconnected' else
                            'Dlouho nebyl přijat žádný platný APRS rámec. Neznamená to jistou poruchu TNC.' if health == 'quiet' else '')}

    def journal_snapshot(self, limit=250, direction=''):
        return {'entries': self.journal.recent(limit, direction),
                'diagnostics': self.diagnostics_snapshot()}

    def objects_snapshot(self):
        return {'objects': list(self.config.data['objects']['entries']),
                'path': self.config.data['objects']['path'],
                'source': self.config.data['igate']['call'],
                'enabled': self.object_schedule_enabled,
                'radio_ready': self.radio_ready}

    def config_backup(self):
        return self.config.export_backup()

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

    def _send_rf_operation(self, info, category, path=None):
        if not self.radio_ready or self.reader is None:
            raise ValueError('USB KISS TNC není připojeno.')
        source = self.config.data['igate']['call']
        path = self.config.data['objects']['path'] if path is None else path
        raw = make_rf_frame(source, path, info)
        if not self.reader.send(encode_kiss_data(raw), category=category):
            self._journal('DROP', 'KISS', source, 'APZKIS', path, info, 'TX queue full')
            raise ValueError('USB TX fronta je obsazená; zkus to později.')
        self._journal('TX', 'KISS', source, 'APZKIS', path, info, 'Queued for USB (not RF confirmed)')
        return 'APRS rámec zařazen do USB KISS fronty. Skutečný RF přenos nelze z PC potvrdit.'

    def _find_object(self, name, kind):
        for entry in self.config.data['objects']['entries']:
            if entry['name'] == name and entry['kind'] == kind:
                return entry
        raise ValueError('Objekt/položka nebyla nalezena.')

    def _execute(self, action, data):
        if action == 'health_save':
            changes = data.get('health')
            if not isinstance(changes, dict):
                raise ValueError('Neplatné prahy diagnostiky.')
            self.config.update({'health': changes})
            self._journal('SYSTEM','HEALTH',outcome='Monitoring thresholds updated')
            return 'Prahy diagnostiky uloženy; ostatní provozní funkce zůstávají beze změny.'
        if action == 'objects_path':
            path = data.get('path')
            self.config.update({'objects': {'path': path}})
            self.object_schedule_enabled = False
            self.object_next_due.clear()
            self._journal('SYSTEM','OBJECT',detail=self.config.data['objects']['path'],outcome='RF path updated; schedule stopped')
            return 'RF cesta uložena. Automatické opakování objektů zastaveno.'
        if action == 'object_save':
            entry = validate_object(data.get('entry'))
            existing = list(self.config.data['objects']['entries'])
            key = (entry['name'], entry['kind'])
            for n, old in enumerate(existing):
                if (old['name'], old['kind']) == key:
                    existing[n] = entry
                    break
            else:
                if len(existing) >= MAX_OBJECTS:
                    raise ValueError('Dosažen limit 20 objektů.')
                existing.append(entry)
            self.object_schedule_enabled = False
            self.object_next_due.clear()
            self.config.update({'objects': {'entries': existing}})
            self._journal('SYSTEM', 'OBJECT', detail=entry['name'], outcome='Saved, scheduler off')
            return 'Objekt uložen bez vysílání. Automatické opakování zastaveno.'
        if action == 'object_remove':
            name, kind = data.get('name'), data.get('kind', 'object')
            self._find_object(name, kind)
            self.object_schedule_enabled = False
            self.object_next_due.clear()
            entries = [x for x in self.config.data['objects']['entries'] if (x['name'], x['kind']) != (name, kind)]
            self.config.update({'objects': {'entries': entries}})
            self._journal('SYSTEM', 'OBJECT', detail=name, outcome='Deleted locally; no kill packet transmitted')
            return 'Objekt odebrán z konfigurace. Pro ukončení veřejného objektu je nutné nejprve odeslat KILL.'
        if action in ('object_send', 'object_kill'):
            if data.get('confirm') is not True:
                raise ValueError('Jednotlivé RF vysílání vyžaduje potvrzení.')
            now = time.monotonic()
            if now - self.last_object_tx < 10:
                raise ValueError('Počkej alespoň 10 sekund mezi objektovými RF rámci.')
            entry = self._find_object(data.get('name'), data.get('kind', 'object'))
            payload = object_info(entry, alive=(action == 'object_send'))
            result = self._send_rf_operation(payload, 'obj:'+entry['name'])
            if action == 'object_kill':
                # Do not resurrect a killed object via a previously enabled timer.
                self.object_schedule_enabled = False
                self.object_next_due.clear()
                entries = list(self.config.data['objects']['entries'])
                for e in entries:
                    if e['name'] == entry['name'] and e['kind'] == entry['kind']:
                        e['repeat'] = False
                self.config.update({'objects': {'entries': entries}})
            self.last_object_tx = now
            self.object_next_due[(entry['kind'], entry['name'])] = now + entry['interval_minutes'] * 60
            return result
        if action == 'objects_on':
            if data.get('confirm') is not True:
                raise ValueError('Potvrď automatické vysílání APRS objektů.')
            if not self.radio_ready or self.reader is None:
                raise ValueError('TNC není připojeno.')
            repeat = [x for x in self.config.data['objects']['entries'] if x['repeat']]
            if not repeat:
                raise ValueError('Žádné uložené objekty nemají povolené opakování.')
            self.object_schedule_enabled = True
            now = time.monotonic()
            self.object_next_due = {(x['kind'],x['name']):now + 15 + index*60 for index,x in enumerate(repeat)}
            self._journal('SYSTEM','OBJECT',detail=str(len(repeat))+' repeat enabled',outcome='Session only')
            return 'Automatické opakování objektů spuštěno. Po restartu služby se samo nezapne.'
        if action == 'objects_off':
            self.object_schedule_enabled = False
            self.object_next_due.clear()
            self._journal('SYSTEM','OBJECT',outcome='Repeater stopped')
            return 'Automatické vysílání APRS objektů zastaveno.'
        if action in ('station_status', 'station_position'):
            if data.get('confirm') is not True:
                raise ValueError('RF vysílání vyžaduje potvrzení.')
            now = time.monotonic()
            if now - self.last_object_tx < 10:
                raise ValueError('Omezujeme RF vysílání na jeden rámec za 10 s.')
            if action == 'station_status':
                payload = status_info(data.get('text'))
            else:
                pos = self.config.data['position']
                if pos['latitude'] is None:
                    raise ValueError('Nejdřív nastav vlastní GPS polohu.')
                payload = position_info(pos['latitude'], pos['longitude'], '/', '&', pos['comment'])
            result = self._send_rf_operation(payload, 'station')
            self.last_object_tx = now
            return result
        if action == 'journal_clear':
            if data.get('confirm') is not True:
                raise ValueError('Potvrď smazání provozního deníku.')
            self.journal.clear()
            self._journal('SYSTEM', 'JOURNAL', outcome='Journal cleared by operator')
            return 'Provozní deník vymazán.'
        if action == 'backup_restore':
            if data.get('confirm') is not True:
                raise ValueError('Potvrď obnovení nastavení a zastavení provozních funkcí.')
            backup = data.get('backup')
            # Validate before disabling existing services or modifying the config.
            from service_config import validate_config
            if not isinstance(backup, dict) or backup.get('format') != 'ok5tvr-config-v1':
                raise ValueError('Neplatný formát zálohy.')
            validate_config(backup.get('config'))
            self._disable_digi()
            self._disable_igate()
            self.object_schedule_enabled = False
            self.object_next_due.clear()
            self.messages.usb_closed()
            previous_port = self.config.data['serial']['port']
            self.config.restore_backup(backup)
            m=self.config.data['messages']
            self.messages.configure(self.config.data['igate']['call'], m['path'], m['auto_ack'],m['retry_seconds'],m['max_attempts'])
            self.digi = self._make_digi()
            self.state.update_digi(self.digi.snapshot())
            self._update_position()
            if previous_port != self.config.data['serial']['port']:
                self._disconnect_reader()
                self.next_serial_attempt = 0
            self._journal('SYSTEM','BACKUP',outcome='Imported; all automatic TX disabled')
            return 'Záloha načtena; iGate, DIGI, ACK a plánované objekty jsou vypnuté. APRS-IS heslo a webové klíče se neimportují.'
        if action == 'save':
            changes = data.get('config', {})
            if not isinstance(changes, dict):
                raise ValueError('Nastavení musí být objekt.')
            if any(not isinstance(changes.get(section, {}), dict) for section in ('digi','messages','objects','health')):
                raise ValueError('Nastavení DIGI a zpráv musí být objekt.')
            requested_digi_autostart = changes.get('digi', {}).get('autostart', False)
            if requested_digi_autostart and data.get('confirm_auto_tx') is not True:
                raise ValueError('Automatický RF TX po startu vyžaduje výslovné potvrzení.')
            if changes.get('messages', {}).get('auto_ack') is True and data.get('confirm_auto_ack') is not True:
                raise ValueError('Zapnutí automatických RF ACK vyžaduje výslovné potvrzení.')
            passcode = data.get('passcode')
            if passcode is not None and not isinstance(passcode, str):
                raise ValueError('Neplatný APRS-IS passcode.')
            previous_port = self.config.data['serial']['port']
            previous_call = self.config.data['igate']['call']
            previous_messages = dict(self.config.data['messages'])
            self.config.update(changes, passcode=passcode)
            if previous_call != self.config.data['igate']['call'] or previous_messages != self.config.data['messages']:
                # Persisted pending transmissions are invalid when callsign/path changes.
                self.messages.usb_closed()
            m = self.config.data['messages']
            self.messages.configure(self.config.data['igate']['call'], m['path'], m['auto_ack'],
                                    m['retry_seconds'], m['max_attempts'])
            self._update_position()
            self.object_schedule_enabled = False
            self.object_next_due.clear()
            # No silent change to an already-running RF DIGI configuration.
            if self.want_digi:
                self._disable_digi()
            self.digi = self._make_digi()
            self.state.update_digi(self.digi.snapshot())
            if self.igate_client:
                self._disable_igate()
            if previous_port != self.config.data['serial']['port']:
                self._disconnect_reader()
                self.next_serial_attempt = 0.0
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
            raw = encode_ui_packet(call, 'APRS', '', '>OK5TVR APRS KISS v1.6 test')
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
                            i['host'], i['port'], own_events)
        client.configure_position(self._beacon_line(),
                                  self.config.data['position']['beacon_interval'])
        self.igate_client = client
        self.igate_events = own_events
        self.state.update_status(igate='Připojuji k APRS-IS')
        client.start()
        LOG.info('Spuštěna iGate RF->APRS-IS %s (%s:%s)', i['call'], i['host'], i['port'])

    def _disable_igate(self):
        old = self.igate_client
        self.igate_client = None
        self.igate_events = None
        if old:
            old.stop.set()
            old.join(timeout=2.5)
        self.state.update_status(igate='Vypnuto')

    def _enable_digi(self):
        if not self.radio_ready or self.reader is None:
            return
        self.digi.start()
        self._journal('SYSTEM','DIGI',outcome='Enabled by operator/config')
        self.reader.digi_allowed.set()
        self.state.update_digi(self.digi.snapshot())
        LOG.warning('RF DIGI ZAPNUTO: %s %s', self.digi.config.call, self.digi.config.mode)

    def _disable_digi(self):
        self.want_digi = False
        if self.reader:
            self.reader.digi_allowed.clear()
        self.digi.stop()
        self.state.update_digi(self.digi.snapshot())
        self._journal('SYSTEM','DIGI',outcome='Disabled')

    def _disconnect_reader(self):
        if self.reader is not None:
            previous = self.reader
            previous.digi_allowed.clear()
            if self.serial_stop:
                self.serial_stop.set()
            previous.join(timeout=1.0)
            self.reader = None
        self.radio_ready = False
        self.usb_disconnected_at = time.monotonic()
        self.object_schedule_enabled = False  # do not resume unattended RF after USB loss
        self.object_next_due.clear()
        self.messages.usb_closed()
        self.digi.stop()
        self.state.update_digi(self.digi.snapshot())
        self.state.update_status(radio='Odpojeno')

    def _connect_tick(self):
        if self.reader is not None or time.monotonic() < self.next_serial_attempt:
            return
        port = find_radio_port(self.config.data['serial']['port'])
        self.next_serial_attempt = time.monotonic() + self.config.data['serial']['retry_seconds']
        if port is None:
            self.stats['usb_discovery_fail'] += 1
            self.state.update_status(radio='USB nenalezeno / více portů; nastav port')
            if time.monotonic() - self.last_serial_warning > 45:
                LOG.warning('USB KISS port nenalezen/nejednoznačný; zvol /dev/ttyACM0 nebo COMx.')
                self.last_serial_warning = time.monotonic()
            return
        self.session += 1
        self.serial_stop = threading.Event()
        self.reader = SerialReader(port, self.config.data['serial']['baud'], self.events,
                                   self.serial_stop, self.session)
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
                self.usb_connect_count += 1
                self.usb_connected_at = time.monotonic()
                self.usb_disconnected_at = None
                self._last_health_alert = None
                self._journal('SYSTEM', 'KISS', detail=str(value), outcome='USB opened; RF health unverified')
                self.radio_ready = True
                self.state.update_status(radio='Připojeno '+str(value))
                LOG.info('USB KISS připojeno: %s', value)
                if self.want_digi:
                    self._enable_digi()
            elif event == 'frame':
                self._on_frame(value)
            elif event == 'tx_written':
                category = value.get('category', '') if isinstance(value, dict) else ''
                self.stats['tx_usb_written'] += 1
                self._journal('TX', 'KISS', detail=category, outcome='USB written; RF unverified')
                self.state.note_tx()
                if isinstance(value, dict) and value.get('category', '').startswith(('msg:', 'msgack:')):
                    self.messages.tx_written(value['category'])
                if isinstance(value, dict) and value.get('category') == 'digi':
                    self.digi.mark_written()
                    self.state.update_digi(self.digi.snapshot())
            elif event == 'tx_error':
                self.stats['tx_usb_errors'] += 1
                self._journal('DROP', 'KISS', detail=str(value), outcome='USB write error')
                LOG.warning('TX USB selhal: %s', value)
                if isinstance(value, dict) and value.get('category', '').startswith(('msg:', 'msgack:')):
                    self.messages.tx_error(value['category'], value.get('error', 'Chyba USB'))
                if isinstance(value, dict) and value.get('category') == 'digi':
                    self.digi.mark_error()
                    self.state.update_digi(self.digi.snapshot())
            elif event == 'invalid':
                self.stats['invalid'] += 1
                self._journal('DROP', 'KISS', detail=value, outcome='Invalid KISS')
            elif event == 'error':
                self.last_usb_error = str(value)[:110]
                self._journal('SYSTEM','KISS',detail=str(value),outcome='Serial error')
                LOG.warning('Chyba USB KISS: %s', value)
                self.state.update_status(radio='Chyba USB: '+str(value)[:95])
            elif event == 'closed':
                self._journal('SYSTEM','KISS',outcome='USB disconnected; reconnect scheduled')
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
                    self._journal('SYSTEM', 'APRS-IS', detail=value, outcome='Connection state')
                    self.state.update_status(igate=value)
                elif event == 'igate_sent':
                    self.stats['igate_written'] += 1
                    self._journal('IS','APRS-IS',detail=value,outcome='Sent to server socket')
                    self.state.note_igate(True)
                elif event == 'igate_beacon':
                    self._journal('IS','APRS-IS',detail=value,outcome='Position beacon sent')
                    self.state.note_beacon()
                elif event == 'igate_error':
                    self._journal('DROP','APRS-IS',detail=value,outcome='Network error')
                    self.state.update_status(igate='Chyba: '+str(value)[:120])
                    LOG.warning('APRS-IS: %s', value)

    def _on_frame(self, packet):
        if (packet.source == '?' or packet.control != 0x03 or packet.pid != 0xf0):
            self.stats['invalid_aprs'] += 1
            self._journal('DROP','KISS',source=packet.source,destination=packet.destination,
                          path=packet.path,detail=packet.summary,outcome='Not a valid APRS UI frame')
            self.state.add(packet)
            return
        self.last_valid_rx_at = time.monotonic()
        self.last_valid_rx_utc = datetime.now(timezone.utc).isoformat(timespec='seconds')
        self.stats['rx_valid'] += 1
        self._journal('RX','KISS', source=packet.source, destination=packet.destination,
                      path=packet.path,detail=packet.summary,outcome=packet.kind)
        msg = self.messages.receive(packet, self.radio_ready)
        if msg:
            LOG.info('APRS zpráva: %s od %s', msg.get('kind'), msg.get('from'))
        if self.digi.enabled and packet.raw_ax25:
            reason = self.digi.receive(packet.raw_ax25)
            if reason:
                direction = 'TX' if reason.startswith('Plánováno') else 'DROP'
                self._journal(direction,'DIGI', packet.source, packet.destination, packet.path,
                              packet.summary,reason)
            self.state.update_digi(self.digi.snapshot())
        self.state.add(packet)
        if self.igate_client and self.igate_client.connected.is_set():
            line, reason = igate_tnc2(packet, self.igate_client.call)
            if line:
                now = time.monotonic()
                key = (packet.source, packet.destination, packet.raw_info)
                if now - self.gate_cache.get(key, float('-inf')) > 30:
                    if self.igate_client.enqueue(line):
                        self.gate_cache[key] = now
                        self._journal('IS','APRS-IS',packet.source,packet.destination,packet.path,
                                      packet.summary,'Queued to APRS-IS')
                    else:
                        self._journal('DROP','APRS-IS',packet.source,packet.destination,packet.path,
                                      packet.summary,'APRS-IS queue full')
                        self.state.note_igate(False)
                else:
                    self._journal('DROP','APRS-IS',packet.source,packet.destination,packet.path,
                                  packet.summary,'Duplicate within 30 s')
                if len(self.gate_cache) > 4000:
                    self.gate_cache = {key:stamp for key,stamp in self.gate_cache.items() if now-stamp < 60}
            else:
                self._journal('DROP','APRS-IS',packet.source,packet.destination,packet.path,
                              packet.summary,reason)
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
            self.digi.mark_queued(p.signature)
            self.state.update_digi(self.digi.snapshot())

    def _object_tick(self):
        if not self.object_schedule_enabled or not self.radio_ready or not self.reader:
            return
        now = time.monotonic()
        if now - self.last_object_tx < 45:
            return
        for entry in self.config.data['objects']['entries']:
            if not entry['repeat']:
                continue
            key = (entry['kind'], entry['name'])
            if now < self.object_next_due.get(key, now+60):
                continue
            try:
                payload = object_info(entry, alive=True)
                self._send_rf_operation(payload, 'obj:'+entry['name'])
            except ValueError as exc:
                self._journal('DROP','OBJECT',detail=entry['name'],outcome=str(exc))
                return
            self.last_object_tx = now
            self.object_next_due[key] = now + entry['interval_minutes'] * 60
            break

    def _health_tick(self):
        now=time.monotonic()
        config=self.config.data['health']
        if not self.radio_ready:
            age=now - (self.usb_disconnected_at or self.started_monotonic)
            alert='usb_offline' if age >= config['disconnect_warning_seconds'] else None
        elif self.usb_connected_at is not None:
            last = self.last_valid_rx_at if self.last_valid_rx_at is not None else self.usb_connected_at
            alert='quiet' if now - last >= config['quiet_warning_minutes']*60 else None
        else:
            alert=None
        if alert != self._last_health_alert:
            if alert:
                self._journal('SYSTEM','HEALTH',outcome=(
                    'USB disconnected (no radio port)' if alert == 'usb_offline'
                    else 'No recent APRS frames; cannot prove firmware failure'))
            elif self._last_health_alert:
                self._journal('SYSTEM','HEALTH',outcome='Status restored')
            self._last_health_alert=alert

    def run(self):
        # Web server always remains independent of Tkinter and can serve a Pi.
        c = self.config.data
        lan = c['web']['lan'] or self.force_lan
        self.web.start(lan=lan, port=c['web']['port'], fallback=False)
        self.running = True
        LOG.info('Web %s:%d (správa jen pomocí soukromého odkazu).',
                 'LAN' if lan else 'localhost', self.web.port)
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
                self._object_tick()
                self._health_tick()
                self.stop.wait(0.08)
        finally:
            self.running = False
            self._disconnect_reader()
            self._disable_igate()
            self.web.close()
            self.messages.close()
            self.journal.close()
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
        print('Odkaz ADMIN poskytuje plnou správu i možnost RF TX – nesdílej jej.')
        return
    service = APRSService(conf, force_lan=args.lan)
    def halt(*_):
        service.stop.set()
    signal.signal(signal.SIGINT, halt)
    signal.signal(signal.SIGTERM, halt)
    service.run()


if __name__ == '__main__':
    main()
