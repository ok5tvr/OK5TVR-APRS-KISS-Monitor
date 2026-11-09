"""Integration checks for local-only APRS map and token-gated geography."""
import json
import unittest
import urllib.error
import urllib.request
from web_panel import HTML, WebPanel
from aprs_features import MonitorState

class MapOfflineTests(unittest.TestCase):
    def test_self_contained_map(self):
        self.assertIn('geography',HTML)
        self.assertIn('map-marker',HTML)
        self.assertIn('Offline mapa',HTML)
        self.assertIn('tile.openstreetmap.org',HTML)
        self.assertNotIn('unpkg.com',HTML)
        self.assertNotIn('maplibre',HTML.lower())
        self.assertNotIn('basemaps.cartocdn.com',HTML)

    def test_local_symbol_sprites_are_served_without_external_network(self):
        import urllib.request
        self.assertIn('aprs-primary.png', HTML)
        self.assertIn('aprs-secondary.png', HTML)
        web=WebPanel(MonitorState())
        try:
            port=web.start(port=0)
            for path in ('aprs-primary.png', 'aprs-secondary.png', 'aprs-overlays.png'):
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/assets/{path}') as r:
                    self.assertEqual(r.headers['Content-Type'], 'image/png')
                    self.assertTrue(r.read().startswith(b'\x89PNG\r\n\x1a\n'))
        finally:
            web.close()

    def test_offline_geography_endpoint(self):
        web=WebPanel(MonitorState())
        try:
            port=web.start(port=0)
            base=f'http://127.0.0.1:{port}'
            with urllib.request.urlopen(base+'/') as r:
                self.assertEqual(r.status,200)
                self.assertIn(b'offline_geography.json',r.read())
            with urllib.request.urlopen(base+'/assets/offline_geography.json') as r:
                self.assertEqual(r.status,200)
                self.assertEqual(r.headers['Content-Type'],'application/json; charset=utf-8')
                obj=json.load(r)
            self.assertGreater(len(obj['world']['land']),100)
            self.assertGreater(len(obj['central']['borders']),5)
            self.assertTrue(any(v[0]=='Plzeň' for v in obj['places']))
        finally:web.close()

if __name__=='__main__':unittest.main()
