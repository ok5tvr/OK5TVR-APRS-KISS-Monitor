"""Same-origin login/session and web navigation tests (no RF hardware)."""
from __future__ import annotations

from http.cookiejar import CookieJar
import json
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from web_auth import LoginThrottle, SessionAuth
from web_panel import WebPanel


class State:
    def snapshot(self):
        return {'rx': 3, 'station_count': 1, 'rf_status': 'USB connected',
                'igate_status': 'Off', 'history': []}


class Operator:
    def __init__(self):
        self.config = SimpleNamespace(
            data={'serial': {'port': 'auto'}, 'display': {'enabled': False}},
            secrets={'web_username': 'ok5tvr'})
        self.commands = []

    def command(self, action, payload):
        self.commands.append((action, payload))
        return 'ok'

    def diagnostics_snapshot(self):
        return {'radio_connected': True, 'usb_port': '/dev/ttyACM0',
                'digi': {'enabled': False, 'tx_written': 0}}

    def public_config(self):
        return {'serial': {'port': 'auto'}, 'display': {'enabled': False}}


class WebLoginTests(unittest.TestCase):
    def setUp(self):
        self.operator = Operator()
        self.panel = WebPanel(State(), operator=self.operator,
                              viewer_token='view-test', admin_token='test-admin-token')
        self.panel.start(lan=True, port=0)
        self.url = 'http://127.0.0.1:' + str(self.panel.port)
        self.cookies = CookieJar()
        self.client = build_opener(HTTPCookieProcessor(self.cookies))

    def tearDown(self):
        self.panel.close()

    def fetch(self, path):
        return self.client.open(self.url + path, timeout=3)

    def post(self, path, payload, csrf=False):
        headers={'Content-Type':'application/json'}
        if csrf:
            headers['X-APRS-CSRF']='1'
        req=Request(self.url+path, method='POST',
                    data=json.dumps(payload).encode(), headers=headers)
        return self.client.open(req, timeout=3)

    def test_login_required_and_clean_navigation(self):
        with self.fetch('/') as response:
            self.assertIn('Přihlášení'.encode('utf-8'), response.read())
            self.assertEqual(response.geturl().split('/')[-1], 'login')
        with self.assertRaises(HTTPError) as ctx:
            self.fetch('/app')
        self.assertEqual(ctx.exception.code,403)
        with self.assertRaises(HTTPError):
            self.fetch('/api/config')

        with self.assertRaises(HTTPError) as ctx:
            self.post('/api/login', {'username':'wrong','token':'test-admin-token'})
        self.assertEqual(ctx.exception.code,401)
        with self.post('/api/login', {'username':'ok5tvr','token':'test-admin-token'}) as response:
            self.assertEqual(response.status,200)
            self.assertIn('HttpOnly', response.headers['Set-Cookie'])
            self.assertIn('SameSite=Strict', response.headers['Set-Cookie'])
        with self.fetch('/app') as response:
            page=response.read().decode()
            self.assertIn('id="tab-home"', page)
            self.assertIn('data-open="map"', page)
            self.assertIn('data-open="messages"', page)
            self.assertNotIn('test-admin-token', page)
        with self.fetch('/map') as response:
            self.assertIn(b'Offline mapa',response.read())
        with self.fetch('/api/config') as response:
            self.assertEqual(response.status,200)

    def test_session_requires_custom_header_for_radio_controls(self):
        self.post('/api/login', {'username':'ok5tvr','token':'test-admin-token'}).close()
        with self.assertRaises(HTTPError) as ctx:
            self.post('/api/control', {'action':'display_set','enabled':True})
        self.assertEqual(ctx.exception.code,403)
        self.assertEqual(self.operator.commands,[])
        with self.post('/api/control', {'action':'display_set','enabled':True}, csrf=True) as response:
            self.assertTrue(json.load(response)['ok'])
        self.assertEqual(self.operator.commands, [('display_set', {'enabled':True})])
        req=Request(self.url+'/api/logout', data=b'{}', method='POST',
                    headers={'X-APRS-CSRF':'1','Origin':'http://malicious.invalid'})
        with self.assertRaises(HTTPError) as ctx:
            self.client.open(req,timeout=3)
        self.assertEqual(ctx.exception.code,403)
        with self.post('/api/logout', {}, csrf=True) as response:
            self.assertTrue(json.load(response)['ok'])
        with self.assertRaises(HTTPError):
            self.fetch('/api/config')

    def test_session_signing_and_expiry(self):
        session=SessionAuth('secret')
        token=session.issue(now=1000)
        self.assertTrue(session.verify(token,now=1001))
        self.assertFalse(session.verify(token,now=1000+12*60*60+1))
        self.assertFalse(session.verify(token[:-1]+'0' if token[-1]!='0' else token[:-1]+'1',now=1001))
        self.assertFalse(SessionAuth('different').verify(token,now=1001))

    def test_per_address_login_throttling(self):
        throttle=LoginThrottle()
        for _ in range(6):
            self.assertTrue(throttle.allowed('192.0.2.1'))
            throttle.failure('192.0.2.1')
        self.assertFalse(throttle.allowed('192.0.2.1'))
        self.assertTrue(throttle.allowed('192.0.2.2'))
        throttle.success('192.0.2.1')
        self.assertTrue(throttle.allowed('192.0.2.1'))


if __name__ == '__main__':
    unittest.main()
