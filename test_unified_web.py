"""Smoke tests for Raspberry unified browser interface (no radio required)."""
from __future__ import annotations
import json
import unittest
import urllib.error
import urllib.request
from types import SimpleNamespace
from urllib.parse import quote
from web_panel import WebPanel


class DummyState:
    def snapshot(self):
        return {"rf_status": "USB disconnected", "rx": 0, "history": []}


class DummyOperator:
    def __init__(self):
        self.config = SimpleNamespace(data={"serial": {"port": "auto"}, "display": {"enabled": True}})

    def public_config(self):
        return {}

    def diagnostics_snapshot(self):
        return {"digi": {"enabled": False}, "telemetry": {}}

    def command(self, action, data):
        return "ok"


class UnifiedWebTest(unittest.TestCase):
    def setUp(self):
        self.panel = WebPanel(DummyState(), operator=DummyOperator(),
                              viewer_token="viewer-test", admin_token="admin-test")
        self.panel.start(lan=True, port=0, fallback=False)
        self.base = "http://127.0.0.1:%d" % self.panel.port

    def tearDown(self):
        self.panel.close()

    def fetch(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as response:
            return response.status, response.read().decode("utf-8")

    def test_unified_requires_admin(self):
        for path in ("/unified", "/unified?key=viewer-test",
                     "/api/ports?key=viewer-test"):
            with self.subTest(path=path):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    self.fetch(path)
                self.assertEqual(error.exception.code, 403)

    def test_seven_tabs_and_legacy_paths(self):
        code, body = self.fetch("/unified?admin=admin-test")
        self.assertEqual(code, 200)
        self.assertIn("OK5TVR APRS KISS", body)
        for tab in ("rx", "map", "messages", "objects", "igate",
                    "telemetry", "diagnostics"):
            self.assertIn('data-tab="%s"' % tab, body)
        for legacy in ("/", "/control", "/messages", "/operations"):
            code, _ = self.fetch(legacy + "?admin=admin-test")
            self.assertEqual(code, 200)

    def test_hdmi_toggle_exists_in_unified_web(self):
        status, content = self.fetch("/unified?admin=admin-test")
        self.assertEqual(status, 200)
        self.assertIn('id="hdmi-display"', content)
        self.assertIn('display_set', content)

    def test_hdmi_status_endpoint_is_local_and_contains_no_tokens(self):
        status, content = self.fetch("/api/local-display")
        self.assertEqual(status, 200)
        data = json.loads(content)
        self.assertTrue(data["enabled"])
        self.assertNotIn("admin", content)
        self.assertNotIn("passcode", content)
        self.assertNotIn("viewer", content)
        self.assertEqual(data["port_configured"], "auto")
        self.assertIsInstance(data["history"], list)

    def test_serial_ports_api(self):
        code, body = self.fetch("/api/ports?admin=admin-test")
        self.assertEqual(code, 200)
        obj = json.loads(body)
        self.assertEqual(obj["selected"], "auto")
        self.assertIsInstance(obj["ports"], list)


if __name__ == "__main__":
    unittest.main()
