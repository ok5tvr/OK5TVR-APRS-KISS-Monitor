"""Headless config, web security, USB KISS loop and local APRS-IS tests. No RF!"""
from __future__ import annotations
import json
import os
import queue
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen, Request

from aprs_features import encode_ui_packet, encode_kiss_data
from aprs_protocol import KissDecoder, decode_ax25
from aprs_service import APRSService
from service_config import ServiceConfig


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def wait(predicate, seconds=5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class FakeSerial:
    incoming = queue.Queue()
    outgoing = queue.Queue()
    def __init__(self, port, baud, timeout=0.2, write_timeout=1):
        self.port, self.baud = port, baud
        self.dtr = False
        self.closed = False
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.closed = True
    def read(self, _count):
        try: return self.incoming.get(timeout=0.08)
        except queue.Empty: return b''
    def write(self, data):
        self.outgoing.put(bytes(data))
        return len(data)
    def flush(self):
        pass


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conf = ServiceConfig(Path(self.tmp.name)/'config.json').load_or_create()
    def tearDown(self):
        self.tmp.cleanup()
    def test_initial_defaults_and_secrets(self):
        self.assertFalse(self.conf.data['igate']['autostart'])
        self.assertFalse(self.conf.data['digi']['autostart'])
        self.assertFalse(self.conf.data['position']['beacon_enabled'])
        self.assertNotIn('igate_passcode', self.conf.path.read_text())
        self.assertNotIn('admin_token', self.conf.path.read_text())
        self.assertEqual(len(self.conf.secrets['admin_token']) >= 32, True)
        if os.name != 'nt':
            self.assertEqual(self.conf.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.conf.secret_path.stat().st_mode & 0o777, 0o600)
    def test_legacy_v16_config_migrates_with_backup_and_tx_disabled(self):
        previous = self.conf.data.copy()
        previous['igate'] = dict(previous['igate'], autostart=True)
        previous['digi'] = dict(previous['digi'], autostart=True,
                                beacon_enabled=True, beacon_transport='rf')
        previous['messages'] = dict(previous['messages'], auto_ack=True)
        previous['health'] = {'quiet_warning_minutes': 30, 'disconnect_warning_seconds': 15}
        previous['objects'] = {'path': 'WIDE1-1', 'entries': [
            {'name': 'TEST', 'kind': 'object', 'latitude': 49.7,
             'longitude': 13.3, 'comment': 'kept in backup'}]}
        self.conf.path.write_text(json.dumps(previous), encoding='utf-8')
        original_token = self.conf.secrets['admin_token']
        loaded = ServiceConfig(self.conf.path).load_or_create()
        backups = list(self.conf.path.parent.glob('config.before-v19-*.json'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text(encoding='utf-8')), previous)
        self.assertEqual(loaded.secrets['admin_token'], original_token)
        self.assertFalse(loaded.data['igate']['autostart'])
        self.assertFalse(loaded.data['digi']['autostart'])
        self.assertFalse(loaded.data['messages']['auto_ack'])
        self.assertFalse(loaded.data['digi']['beacon_enabled'])
        self.assertNotIn('health', loaded.data)
        self.assertNotIn('objects', loaded.data)

    def test_unknown_config_still_fails_without_rewriting(self):
        raw = dict(self.conf.data)
        raw['health'] = {}
        raw['unexpected_section'] = {'foo': 1}
        before = json.dumps(raw)
        self.conf.path.write_text(before, encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Nepodporovaná sekce'):
            ServiceConfig(self.conf.path).load_or_create()
        self.assertEqual(self.conf.path.read_text(encoding='utf-8'), before)
        self.assertFalse(list(self.conf.path.parent.glob('config.before-v19-*.json')))

    def test_validation_rejects_and_preserves_config(self):
        good = self.conf.data['position']['latitude']
        for bad in ({'position': {'latitude': 91, 'longitude': 13}},
                    {'digi': {'max_per_min': 100}},
                    {'igate': {'call': 'WRONG-23'}},
                    {'position': {'beacon_enabled': True}},
                    {'web': {'port': 3}},
                    {'serial': {'retry_seconds': 0}}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.conf.update(bad)
            self.assertEqual(self.conf.data['position']['latitude'], good)
        self.conf.update({'position': {'latitude': 49.77, 'longitude': 13.29,
                                       'beacon_enabled': True}}, passcode='12345')
        self.assertTrue(self.conf.public_view()['igate']['has_passcode'])
        self.assertNotIn('12345', self.conf.path.read_text())
        self.assertIn('12345', self.conf.secret_path.read_text())
        prev = self.conf.secrets['viewer_token']
        other = ServiceConfig(self.conf.path).load_or_create()
        self.assertEqual(other.secrets['viewer_token'], prev)


class HeadlessIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conf = ServiceConfig(Path(self.tmp.name)/'config.json').load_or_create()
        self.port = free_port()
        self.conf.update({'serial': {'port': 'FAKEUSB'}, 'web': {'port': self.port}})
        FakeSerial.incoming = queue.Queue()
        FakeSerial.outgoing = queue.Queue()
        self.patch_serial = patch('aprs_serial.serial', SimpleNamespace(Serial=FakeSerial))
        self.patch_serial.start()
        self.service = APRSService(self.conf)
        self.thread = threading.Thread(target=self.service.run, daemon=True)
        self.thread.start()
        self.assertTrue(wait(lambda: self.service.radio_ready), 'Fake KISS serial did not open')

    def tearDown(self):
        self.service.stop.set()
        self.thread.join(timeout=5)
        self.patch_serial.stop()
        self.tmp.cleanup()
        self.assertFalse(self.thread.is_alive(), 'Service failed to stop')

    @property
    def base(self):
        return f'http://127.0.0.1:{self.port}'

    def api(self, action, expect=200, auth=True, **kwargs):
        headers={'Content-Type':'application/json'}
        if auth:
            headers['X-APRS-Admin']=self.conf.secrets['admin_token']
        request=Request(self.base+'/api/control', data=json.dumps({'action': action,**kwargs}).encode(),
                        headers=headers, method='POST')
        try:
            with urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, expect)
                return json.load(response)
        except HTTPError as e:
            self.assertEqual(e.code, expect)
            return json.load(e)

    def test_api_auth_config_and_browser(self):
        with urlopen(self.base+'/map') as r:
            self.assertIn(b'Offline mapa', r.read())
        with self.assertRaises(HTTPError) as e:
            urlopen(self.base+'/control')
        self.assertEqual(e.exception.code,403)
        with urlopen(self.base+'/control?admin='+self.conf.secrets['admin_token']) as r:
            self.assertIn(b'APRS DIGI',r.read())
        with self.assertRaises(HTTPError):
            urlopen(self.base+'/api/config')
        with urlopen(self.base+'/api/config?admin='+self.conf.secrets['admin_token']) as r:
            view=json.load(r)
        self.assertNotIn('igate_passcode',str(view))
        self.assertNotIn('viewer_token', view)
        self.assertIn('error', self.api('digi_on', expect=403, auth=False))
        self.assertEqual(self.api('digi_on', expect=400)['ok'],False)
        self.assertEqual(self.api('save',config={'digi':{'autostart':True}},expect=400)['ok'],False)
        self.assertEqual(self.api('save',config={'digi':{'delay_s':0.0}})['ok'],True)
        self.assertEqual(self.api('tx_test',expect=400)['ok'],False)

    def test_hdmi_display_toggle_has_no_radio_side_effects(self):
        self.assertFalse(self.conf.data['display']['enabled'])
        before = self.conf.data['igate']['autostart'], self.conf.data['digi']['autostart']
        self.assertTrue(self.service.radio_ready)
        self.assertEqual(self.api('display_set', enabled=True)['ok'], True)
        self.assertTrue(self.conf.data['display']['enabled'])
        self.assertEqual((self.conf.data['igate']['autostart'],
                          self.conf.data['digi']['autostart']), before)
        self.assertTrue(self.service.radio_ready)
        self.assertTrue(FakeSerial.outgoing.empty())
        self.assertEqual(self.api('display_set', enabled="yes", expect=400)['ok'], False)
        self.assertTrue(self.conf.data['display']['enabled'])
        self.assertEqual(self.api('display_set', enabled=False)['ok'], True)
        self.assertFalse(self.conf.data['display']['enabled'])

    def test_usb_rx_then_manual_tx_and_digi_on_off(self):
        raw=encode_ui_packet('OK5ABC-7','APRS','WIDE1-1','!4944.30N/01322.42E>TEST RF')
        FakeSerial.incoming.put(encode_kiss_data(raw))
        self.assertTrue(wait(lambda:self.service.state.rx == 1))
        snap=self.service.state.snapshot()
        self.assertEqual(snap['station_count'],1)
        self.assertEqual(snap['position_count'],1)
        self.assertEqual(snap['digi']['tx_written'],0)
        self.assertTrue(FakeSerial.outgoing.empty(), 'RX-only startup emitted RF')
        self.assertEqual(self.api('tx_test',confirm=True)['ok'],True)
        self.assertTrue(wait(lambda:not FakeSerial.outgoing.empty()))
        outgoing=FakeSerial.outgoing.get()
        contents=KissDecoder().feed(outgoing)
        self.assertEqual(len(contents),1)
        self.assertEqual(decode_ax25(contents[0][1:]).source,'OK5TVR-10')
        self.assertEqual(self.api('tx_test',confirm=True,expect=400)['ok'],False)
        self.api('save',config={'digi':{'delay_s':0.0}})
        self.api('digi_on',confirm=True)
        FakeSerial.incoming.put(encode_kiss_data(
            encode_ui_packet('OK5ABC-7','APRS','WIDE1-1','>UNIQUE DIGI')
        ))
        self.assertTrue(wait(lambda:not FakeSerial.outgoing.empty()))
        repeated=FakeSerial.outgoing.get()
        frame=decode_ax25(KissDecoder().feed(repeated)[0][1:])
        self.assertEqual(frame.path,'OK5TVR-3*')
        self.assertTrue(wait(lambda:self.service.state.snapshot()['digi']['tx_written'] == 1))
        self.api('digi_off')
        FakeSerial.incoming.put(encode_kiss_data(encode_ui_packet('OK5ABC-7','APRS','WIDE1-1','>NEW DATA')))
        self.assertTrue(wait(lambda:self.service.state.rx >= 3))
        self.assertTrue(FakeSerial.outgoing.empty(), 'DIGI off still emitted RF')

    def test_reconnect_after_usb_read_error_without_unrequested_rf_tx(self):
        self.api('save', config={'serial': {'retry_seconds': 2}})
        # A read failure represents a disconnected or faulted USB cable.
        FakeSerial.incoming.put(OSError('USB disconnected'))
        self.assertTrue(wait(lambda: not self.service.radio_ready, 2))
        self.assertTrue(wait(lambda: self.service.radio_ready, 6))
        self.assertFalse(self.service.digi.enabled)
        self.assertTrue(FakeSerial.outgoing.empty())
        FakeSerial.incoming.put(encode_kiss_data(encode_ui_packet(
            'OK5ABC-7', 'APRS', 'WIDE1-1', '>after reconnect')))
        self.assertTrue(wait(lambda: self.service.state.rx >= 1, 3))

    def test_verified_aprsis_rf_to_internet(self):
        server=socket.socket();server.bind(('127.0.0.1',0));server.listen(1)
        port=server.getsockname()[1]
        received=[];ready=threading.Event()
        def run_server():
            try:
                server.settimeout(5)
                conn,_=server.accept()
                with conn:
                    conn.settimeout(5)
                    conn.sendall(b'# local test server\r\n')
                    buf=b''
                    while b'\n' not in buf:
                        buf+=conn.recv(2048)
                    received.append(buf.decode('ascii','replace'))
                    conn.sendall(b'# logresp OK5TVR-10 verified, server TEST\r\n')
                    buf=b''
                    while b'\n' not in buf:
                        buf+=conn.recv(2048)
                    received.append(buf.decode('latin-1'))
            finally:
                ready.set();server.close()
        threading.Thread(target=run_server,daemon=True).start()
        self.api('save',config={'igate':{'host':'127.0.0.1','port':port}},passcode='12345')
        self.api('igate_on',confirm=True)
        self.assertTrue(wait(lambda:self.service.igate_client is not None and self.service.igate_client.connected.is_set()))
        packet=encode_ui_packet('OK5ABC-7','APRS','WIDE1-1','>RF-to-IS TEST')
        FakeSerial.incoming.put(encode_kiss_data(packet))
        self.assertTrue(ready.wait(5), 'Local APRS-IS server received no RF packet')
        self.assertIn('vers OK5TVR-KISS 1.7',received[0])
        self.assertIn(',qAO,OK5TVR-10:>RF-to-IS TEST', received[1])
        self.assertTrue(FakeSerial.outgoing.empty(), 'Internet test unexpectedly emitted RF')

if __name__=='__main__':unittest.main()
