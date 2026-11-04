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
        self.assertIn('basemaps.cartocdn.com',HTML)
        self.assertNotIn('unpkg.com',HTML)
        self.assertNotIn('maplibre',HTML.lower())
        self.assertNotIn('tile.openstreetmap.org',HTML)

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
