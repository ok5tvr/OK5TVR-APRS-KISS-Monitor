"""Regression tests for one-language-control UI and historic APRS heard map.

Run without a browser or radio; Node.js optionally validates the embedded scripts.
"""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class WebUXV24Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.unified = (ROOT / "web_unified.html").read_text(encoding="utf-8")
        cls.map = (ROOT / "web_dashboard.html").read_text(encoding="utf-8")
        cls.locale = (ROOT / "web_locale.js").read_text(encoding="utf-8")
        cls.bbs = (ROOT / "web_bbs.html").read_text(encoding="utf-8")
        cls.operations = (ROOT / "web_operations.html").read_text(encoding="utf-8")

    def test_exactly_one_settings_language_selector_no_header_duplicate(self):
        self.assertEqual(self.unified.count('id="ui-language-choice"'), 1)
        self.assertIn('id="tab-igate"', self.unified)
        self.assertIn('id="language-preferences"', self.unified)
        self.assertNotIn('id="language"', self.unified)
        self.assertNotIn('id="language"', self.operations)
        self.assertNotIn('ui-language-selector', self.locale)
        self.assertNotIn('createElement("select")', self.locale)
        self.assertIn('addEventListener("change", () => apply(choice.value))', self.locale)
        self.assertIn('ok5tvr:language', self.unified)
        self.assertIn('frame.contentWindow.OK5TVRLocale.setLanguage', self.unified)
        self.assertIn('web_locale.js', self.bbs)

    def test_homepage_cards_in_numerical_order(self):
        block = self.unified.split('<div class="home-links">', 1)[1].split(
            '</div>\n</section>\n<section class="view" id="tab-rx"', 1)[0]
        numbers = list(map(int, re.findall(r'<strong>(\d\d) · ', block)))
        self.assertEqual(numbers, list(range(1, 15)))

    def test_heard_map_matches_historical_stats_and_receiver_filter(self):
        heard = self.unified.split('id="tab-heard"', 1)[1].split(
            'id="tab-bbs"', 1)[0]
        for name in ('heard-stations-count', 'heard-direct-count',
                     'heard-direct-packets', 'heard-via-packets', 'heard-dx-km',
                     'heard-map-frame', 'heard-period', 'heard-device',
                     'heard-rows', 'heard-summary'):
            with self.subTest(name=name):
                self.assertIn('id="' + name + '"', heard)
        self.assertLess(heard.index('id="heard-map-frame"'),
                        heard.index('id="heard-rows"'))
        self.assertIn('get("/api/heard"+params)', self.unified)
        self.assertIn('"/map?heard=1&embedded=1&minutes="', self.unified)
        self.assertIn('&receiver="+encodeURIComponent(receiver)', self.unified)
        self.assertIn("const HEARD_MODE=urlParams.get('heard')==='1'", self.map)
        self.assertIn("urlParams.get('embedded')==='1'", self.map)
        self.assertIn("fetch(authPath('/api/heard?'+params)", self.map)
        self.assertIn("positions=(payload.stations||[])", self.map)
        self.assertIn("setInterval(refresh,HEARD_MODE?60000:2500)", self.map)
        self.assertIn('body.heard-embedded #map', self.map)
        # Do not misrepresent live APRS state as historic coverage.
        self.assertRegex(self.map, r'if\(HEARD_MODE\)\{[\s\S]*?return;\s*\}\s*const response=await fetch\(authPath\(\'/api/state\'\)')

    def test_bilingual_bbs_and_safe_cross_page_language(self):
        self.assertIn('id="bbs-commands-cs"', self.bbs)
        self.assertIn('id="bbs-commands-en"', self.bbs)
        self.assertIn('updateHelpLanguage()', self.bbs)
        self.assertIn("window.addEventListener('ok5tvr:language'", self.operations)
        self.assertIn('"Language / Jazyk"', self.locale)

    def test_relevant_translation_coverage(self):
        for label in ('"RX rámce":', '"Jazyk webového rozhraní":',
                      '"11 · Mapa RF doslechu":', '"13 · Automatická upozornění":',
                      '"Nastavení osobní BBS":', '"Stav BBS a aktivního AX.25 spojení":',
                      '"Mapa přijatých stanic":', '"Nejvzdálenější GPS":'):
            self.assertIn(label, self.locale)

    def test_no_duplicate_html_id(self):
        for file in ('web_unified.html', 'web_dashboard.html', 'web_bbs.html'):
            html = (ROOT / file).read_text(encoding="utf-8")
            # Only the actual HTML, not the JavaScript strings.
            html = html.split('<script src=', 1)[0]
            ids = re.findall(r'\bid="([^"]+)"', html)
            self.assertEqual(len(ids), len(set(ids)), file)

    @unittest.skipUnless(shutil.which("node"), "Node.js optional")
    def test_locale_library_javascript_parse(self):
        code = self.locale
        proc = subprocess.run(['node', '--check'], input=code,
                              text=True, capture_output=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
