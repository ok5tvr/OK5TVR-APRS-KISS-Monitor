"""Verify that APRS message page can load its JavaScript without syntax errors.

Regression: the malformed Inbox 'ID' concatenation prevented all JS,
leaving KISS status and Inbox permanently at loading placeholders.
"""
import re
import shutil
import subprocess
from pathlib import Path
import unittest


class MessagePageJavaScriptTests(unittest.TestCase):
    def test_message_page_has_valid_inbox_id_expression(self):
        html=(Path(__file__).parent/'web_messages.html').read_text(encoding='utf-8')
        self.assertIn(" · ID '+(msg.message_id||tr('bez ID'))",html)
        self.assertNotIn(" · ID +(msg.message_id||tr(",html)
        self.assertIn("fetch(authUrl('/api/messages')",html)

    @unittest.skipUnless(shutil.which('node'),'Node.js optional')
    def test_message_page_scripts_parse(self):
        html=(Path(__file__).parent/'web_messages.html').read_text(encoding='utf-8')
        snippets=re.findall(r'<script(?:\s[^>]*)?>([\s\S]*?)</script>',html)
        self.assertGreater(len(snippets),0)
        for code in snippets:
            if not code.strip(): continue
            check=subprocess.run(['node','--check'],input=code,text=True,
                                 capture_output=True,timeout=10)
            self.assertEqual(check.returncode,0,check.stderr)


if __name__=='__main__':
    unittest.main()
