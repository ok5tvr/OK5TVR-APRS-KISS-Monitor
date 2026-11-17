"""Static JavaScript parse checks and feature presence for v2.3 web pages."""
import re
import shutil
import subprocess
from pathlib import Path
import unittest


class WebV23Tests(unittest.TestCase):
    def test_important_views_exist(self):
        root=Path(__file__).parent
        unified=(root/'web_unified.html').read_text(encoding='utf-8')
        dashboard=(root/'web_dashboard.html').read_text(encoding='utf-8')
        for label in (
            'tab-heard','tab-chat2','tab-alerts','tnc-tx-gap',
            'sec1-enabled','sec2-enabled','heard-csv','chat2-bulletins',
            'alert-mqtt','message_read','message_blocklist','alerts_save'):
            with self.subTest(label=label):self.assertIn(label,unified)
        for label in ('map-import','importMapFile','drawImportedLayers',
                      'map-clear-import','getElementsByTagName','heard'):
            with self.subTest(label=label):self.assertIn(label,dashboard)

    def test_message_page_loader_and_ssid_controls(self):
        html=(Path(__file__).parent/'web_messages.html').read_text(encoding='utf-8')
        self.assertIn('id="add_digi_alias"',html)
        self.assertIn('id="messages_load_error"',html)
        self.assertIn("msg.message_id||tr('bez ID')",html)
        self.assertNotIn(" · ID +(msg.message_id||tr(",html)
        self.assertIn("last.digi_call",html)
        self.assertIn("last.receive_calls",html)

    def test_bbs_html_and_access_controls(self):
        root=Path(__file__).parent
        html=(root/'web_bbs.html').read_text(encoding='utf-8')
        web=(root/'web_unified.html').read_text(encoding='utf-8')
        self.assertIn('id="activate"',html)
        self.assertIn('id="deactivate"',html)
        self.assertIn('id="bbs-call"',html)
        self.assertIn('id="messages"',html)
        self.assertIn('"X-APRS-CSRF":"1"',html)
        self.assertIn('data-tab="bbs"',web)
        self.assertIn('bbs:"/bbs"',web)

    @unittest.skipUnless(shutil.which('node'),'Node.js is optional for JS syntax checks')
    def test_inline_scripts_parse_as_javascript(self):
        for path in (Path(__file__).parent/'web_unified.html',
                     Path(__file__).parent/'web_dashboard.html',
                     Path(__file__).parent/'web_operations.html',
                     Path(__file__).parent/'web_messages.html',
                     Path(__file__).parent/'web_bbs.html'):
            source=path.read_text(encoding='utf-8')
            scripts=re.findall(r'<script(?:\s[^>]*)?>([\s\S]*?)</script>',source)
            scripts=[script for script in scripts if script.strip()]
            self.assertTrue(scripts,str(path))
            for script in scripts:
                result=subprocess.run(['node','--check'],input=script,
                    text=True,capture_output=True,timeout=10)
                self.assertEqual(result.returncode,0,f'{path}: {result.stderr[:1200]}')


if __name__=='__main__':
    unittest.main()
