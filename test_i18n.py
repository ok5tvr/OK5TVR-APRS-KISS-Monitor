"""Localization regression tests; does not require a browser or radio."""
from pathlib import Path
import json
import re
import tempfile
import unittest
from unittest.mock import patch

from desktop_locale import translate
import aprs_station

BASE = Path(__file__).resolve().parent


class LocaleTests(unittest.TestCase):
    def test_desktop_translations_preserve_protocol_data(self):
        self.assertEqual(translate('Sériový port', 'en'), 'Serial port')
        self.assertEqual(translate('Připojit', 'en'), 'Connect')
        self.assertEqual(translate('Připojit', 'cs'), 'Připojit')
        self.assertEqual(translate('OK5TVR>APRS,WIDE1-1:>TEST', 'en'),
                         'OK5TVR>APRS,WIDE1-1:>TEST')

    def test_desktop_language_persists_without_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = Path(folder) / 'prefs.json'
            with patch.object(aprs_station, 'SETTINGS', settings):
                aprs_station.save_settings({'ui_language': 'en', 'igate_call': 'OK5TVR-10'})
                self.assertEqual(aprs_station.load_settings()['ui_language'], 'en')
                self.assertNotIn('passcode', settings.read_text('utf-8'))

    def test_all_web_pages_load_local_translation_and_keep_kiss_protocol(self):
        for filename in ('web_dashboard.html', 'web_control.html', 'web_messages.html'):
            with self.subTest(filename=filename):
                markup = (BASE / filename).read_text('utf-8')
                self.assertIn('<script src="/assets/web_locale.js"></script>', markup)
                self.assertIn('window.OK5TVRLocale.tr', markup)
                self.assertIn('USB', markup)
                self.assertIn('KISS', markup)
        js = (BASE / 'web_locale.js').read_text('utf-8')
        self.assertIn('"Map of received APRS positions"', js)
        self.assertIn('"New APRS message"', js)
        self.assertIn('"Save configuration"', js)
        self.assertIn('ok5tvr.aprs.ui.language', js)
        self.assertIn('data-untranslated', js)

    def test_web_panel_serves_translation_with_no_auth_secrets(self):
        from web_panel import WebPanel
        from aprs_features import MonitorState
        from urllib.request import urlopen
        panel = WebPanel(MonitorState(), viewer_token='TEST_VIEWER_TOKEN', admin_token='TEST_ADMIN_TOKEN')
        try:
            port = panel.start(port=0)
            with urlopen(f'http://127.0.0.1:{port}/assets/web_locale.js', timeout=3) as response:
                self.assertIn('javascript', response.headers['Content-Type'])
                code = response.read().decode('utf-8')
            self.assertIn('Language / Jazyk', code)
            self.assertNotIn('TEST_ADMIN_TOKEN', code)
            self.assertNotIn('TEST_VIEWER_TOKEN', code)
        finally:
            panel.close()


if __name__ == '__main__':
    unittest.main()
