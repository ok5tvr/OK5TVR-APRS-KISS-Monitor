"""Full-page routes, centralized settings and read-only launcher regressions."""
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from aprs_service import APRSService
from service_config import ServiceConfig
from web_panel import WebPanel
from web_views import SETTINGS_ROUTES


class Elements(HTMLParser):
    def __init__(self,html):
        super().__init__();self.tags=[];self.feed(html)
    def handle_starttag(self,tag,attrs):self.tags.append((tag,dict(attrs)))
    def by_id(self,name):return next(attrs for _,attrs in self.tags if attrs.get('id')==name)


class FullPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.service=APRSService(ServiceConfig(Path(self.tmp.name)/'config.json').load_or_create())
        self.panel=WebPanel(self.service.state,self.service,admin_token='admin-nav-test')
        self.panel.start(port=0)
        self.root=f'http://127.0.0.1:{self.panel.port}'
    def tearDown(self):
        self.panel.close()
        for name in ('bbs','secondary','alerts','archive','messages','journal'):getattr(self.service,name).close()
        self.tmp.cleanup()
    def fetch(self,path,admin=True):
        if admin:path+=('&' if '?' in path else '?')+'admin=admin-nav-test'
        with urlopen(self.root+path,timeout=3) as response:return response.read().decode()

    def test_launcher_has_no_mode_switches_or_subwindows(self):
        html=self.fetch('/app');parsed=Elements(html)
        self.assertFalse(any(tag=='iframe' for tag,_ in parsed.tags))
        for button in ('open-aprs','open-bbs','open-settings'):parsed.by_id(button)
        parsed.by_id('terminal-output');parsed.by_id('terminal-pause');parsed.by_id('terminal-scroll')
        self.assertNotIn('mode_set',html)
        self.assertNotIn('id="mode-off"',html)
        self.assertNotIn('id="station-settings"',html)

    def test_all_settings_routes_require_admin_and_have_mode_controls(self):
        for route,_,_ in SETTINGS_ROUTES:
            with self.subTest(route=route):
                with self.assertRaises(HTTPError) as err:self.fetch(route,admin=False)
                self.assertEqual(err.exception.code,403)
                html=self.fetch(route);parsed=Elements(html)
                body=next(attrs for tag,attrs in parsed.tags if tag=='body')
                self.assertEqual(body['data-page-kind'],'settings')
                self.assertEqual({a['data-mode'] for _,a in parsed.tags if 'data-mode' in a},{'aprs','bbs','off'})
                self.assertIn('/settings/bbs',html)
        with self.assertRaises(HTTPError) as err:self.fetch('/settings/advanced?tab=map')
        self.assertEqual(err.exception.code,400)

    def test_operating_pages_are_full_page_and_config_controls_are_settings_only(self):
        for route in ('/aprs','/bbs','/messages','/operations','/objects'):
            with self.subTest(route=route):
                html=self.fetch(route);parsed=Elements(html)
                self.assertFalse(any('data-mode' in attrs for _,attrs in parsed.tags))
                self.assertIn('id="global-navigation"',html)
        self.assertIn('settings-only',Elements(self.fetch('/bbs')).by_id('bbs-configuration')['class'])
        self.assertIn('settings-only',Elements(self.fetch('/bbs')).by_id('server-switches')['class'])
        self.assertIn('settings-only',Elements(self.fetch('/messages')).by_id('message-settings')['class'])
        home=Elements(self.fetch('/settings'))
        self.assertFalse(any(tag=='iframe' for tag,_ in home.tags))
        home.by_id('base-call')

    def test_objects_api_is_admin_only_and_map_has_no_statistics(self):
        with self.assertRaises(HTTPError) as err:self.fetch('/api/objects',admin=False)
        self.assertEqual(err.exception.code,403)
        state=json.loads(self.fetch('/api/objects'))
        self.assertEqual(state['entries'],[]);self.assertFalse(state['active'])
        html=self.fetch('/map');parsed=Elements(html)
        parsed.by_id('map')
        self.assertFalse(any(attrs.get('id') in ('rx15','avg15','rx','digi_tx') for _,attrs in parsed.tags))
        self.assertIn('data-admin-target="objects"',html)

    def test_get_navigation_does_not_change_mode_or_rf_state(self):
        before=self.service.config.public_view()
        for route in ('/app','/aprs','/bbs','/settings','/settings/aprs','/settings/bbs'):
            self.fetch(route)
        self.assertEqual(self.service.config.public_view(),before)
        self.assertEqual(self.service.operating_mode,'aprs')
        self.assertFalse(self.service.bbs.active)
        self.assertFalse(self.service.digi.enabled)
        self.assertIsNone(self.service.igate_client)


if __name__=='__main__':unittest.main()
