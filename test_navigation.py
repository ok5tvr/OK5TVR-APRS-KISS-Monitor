"""Navigation regression tests: public map must not grant RF/admin access."""
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
import unittest

from aprs_features import MonitorState
from web_panel import WebPanel


class Operator:
    def public_config(self):
        return {'serial': {'port': 'COM7'}}


class NavigationTests(unittest.TestCase):
    def test_navigation_present_and_localized(self):
        base = Path(__file__).parent
        map_html = (base / 'web_dashboard.html').read_text(encoding='utf-8')
        operations = (base / 'web_operations.html').read_text(encoding='utf-8')
        messages = (base / 'web_messages.html').read_text(encoding='utf-8')
        desktop = (base / 'aprs_kiss_monitor.py').read_text(encoding='utf-8')
        for element in ['nav-control', 'nav-messages', 'nav-objects', 'nav-diagnostics']:
            self.assertIn('id="' + element + '"', map_html)
        self.assertIn('id="objects"', operations)
        self.assertIn('id="diagnostics"', operations)
        self.assertIn('id="objects_nav"', messages)
        self.assertIn('id="diagnostics_nav"', messages)
        self.assertIn('self.open_service_page("messages")', desktop)
        self.assertIn('self.open_service_page("operations", "objects")', desktop)
        self.assertIn('self.open_service_page("operations", "diagnostics")', desktop)
        self.assertIn('const adminToken=', map_html)

    def test_read_only_map_has_visible_links_but_no_admin_access(self):
        panel = WebPanel(MonitorState())
        panel.start(port=0)
        try:
            root = f'http://127.0.0.1:{panel.port}'
            with urlopen(root + '/', timeout=3) as response:
                content = response.read().decode('utf-8')
            self.assertIn('id="nav-messages"', content)
            with urlopen(root + '/api/capabilities', timeout=3) as response:
                self.assertFalse(json.loads(response.read())['admin_enabled'])
            for url in ['/messages', '/operations', '/control']:
                with self.assertRaises(HTTPError) as error:
                    urlopen(root + url, timeout=3)
                self.assertEqual(error.exception.code, 403)
        finally:
            panel.close()

    def test_authenticated_navigation_only_for_admin_key(self):
        panel = WebPanel(MonitorState(), Operator(), viewer_token='view_token_abcdefgh', admin_token='admin_token_abcdefghijklmnopqrstuvwxyz')
        panel.start(port=0)
        try:
            root = f'http://127.0.0.1:{panel.port}'
            with urlopen(root + '/api/capabilities', timeout=3) as response:
                self.assertTrue(json.loads(response.read())['admin_enabled'])
            with urlopen(root + '/api/config?admin=' + panel.admin_token, timeout=3) as response:
                self.assertEqual(json.loads(response.read())['serial']['port'], 'COM7')
            for url in ['/messages', '/operations', '/control']:
                with self.assertRaises(HTTPError) as error:
                    urlopen(root + url + '?key=' + panel.token, timeout=3)
                self.assertEqual(error.exception.code, 403)
                with urlopen(root + url + '?admin=' + panel.admin_token, timeout=3) as response:
                    self.assertEqual(response.status, 200)
        finally:
            panel.close()


if __name__ == '__main__':
    unittest.main()
