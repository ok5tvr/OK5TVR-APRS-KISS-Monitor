#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OK5TVR APRS v1.4: headless Windows/Linux KISS receiver, RF->IS iGate and DIGI.

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
        if action == 'save':
            changes = data.get('config', {})
            if not isinstance(changes, dict):
                raise ValueError('Nastavení musí být objekt.')
            if any(not isinstance(changes.get(section, {}), dict) for section in ('digi','messages')):
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
            raw = encode_ui_packet(call, 'APRS', '', '>OK5TVR APRS KISS v1.3 test')
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
        self.reader.digi_allowed.set()
        self.state.update_digi(self.digi.snapshot())
        LOG.warning('RF DIGI ZAPNUTO: %s %s', self.digi.config.call, self.digi.config.mode)

    def _disable_digi(self):
        self.want_digi = False
        if self.reader:
            self.reader.digi_allowed.clear()
        self.digi.stop()
        self.state.update_digi(self.digi.snapshot())

    def _disconnect_reader(self):
        if self.reader is not None:
            previous = self.reader
            previous.digi_allowed.clear()
            if self.serial_stop:
                self.serial_stop.set()
            previous.join(timeout=1.0)
            self.reader = None
        self.radio_ready = False
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
                self.radio_ready = True
                self.state.update_status(radio='Připojeno '+str(value))
                LOG.info('USB KISS připojeno: %s', value)
                if self.want_digi:
                    self._enable_digi()
            elif event == 'frame':
                self._on_frame(value)
            elif event == 'tx_written':
                self.state.note_tx()
                if isinstance(value, dict) and value.get('category', '').startswith(('msg:', 'msgack:')):
                    self.messages.tx_written(value['category'])
                if isinstance(value, dict) and value.get('category') == 'digi':
                    self.digi.mark_written()
                    self.state.update_digi(self.digi.snapshot())
            elif event == 'tx_error':
                LOG.warning('TX USB selhal: %s', value)
                if isinstance(value, dict) and value.get('category', '').startswith(('msg:', 'msgack:')):
                    self.messages.tx_error(value['category'], value.get('error', 'Chyba USB'))
                if isinstance(value, dict) and value.get('category') == 'digi':
                    self.digi.mark_error()
                    self.state.update_digi(self.digi.snapshot())
            elif event == 'invalid':
                self.stats['invalid'] += 1
            elif event == 'error':
                LOG.warning('Chyba USB KISS: %s', value)
                self.state.update_status(radio='Chyba USB: '+str(value)[:95])
            elif event == 'closed':
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
                elif event == 'igate_sent':
                    self.state.note_igate(True)
                elif event == 'igate_beacon':
                    self.state.note_beacon()
                elif event == 'igate_error':
                    self.state.update_status(igate='Chyba: '+str(value)[:120])
                    LOG.warning('APRS-IS: %s', value)

    def _on_frame(self, packet):
        msg = self.messages.receive(packet, self.radio_ready)
        if msg:
            LOG.info('APRS zpráva: %s od %s', msg.get('kind'), msg.get('from'))
        if self.digi.enabled and packet.raw_ax25:
            self.digi.receive(packet.raw_ax25)
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
                    else:
                        self.state.note_igate(False)
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
            self.digi.mark_queued(p.signature)
            self.state.update_digi(self.digi.snapshot())

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
                self.stop.wait(0.08)
        finally:
            self.running = False
            self._disconnect_reader()
            self._disable_igate()
            self.web.close()
            self.messages.close()
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