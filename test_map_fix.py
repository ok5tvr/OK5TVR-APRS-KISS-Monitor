import unittest
from web_panel import HTML, WebPanel
from aprs_features import MonitorState

class MapFixTests(unittest.TestCase):
 def test_map_now_self_hosted(self):
  self.assertIn('offline_geography.json',HTML)
  self.assertIn('canvas id="geography"',HTML)
  self.assertNotIn('tiles.openfreemap.org',HTML)
  self.assertNotIn('unpkg.com',HTML)
 def test_referrer_header(self):
  import urllib.request
  w=WebPanel(MonitorState())
  try:
   port=w.start(port=0)
   with urllib.request.urlopen(f'http://127.0.0.1:{port}/') as res:
    self.assertEqual(res.headers['Referrer-Policy'],'strict-origin-when-cross-origin')
    self.assertIn(b'Offline mapa',res.read())
  finally:w.close()

if __name__=='__main__':unittest.main()
