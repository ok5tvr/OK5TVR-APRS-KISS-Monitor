"""Integration smoke test for v2.1 service, read-only web APIs and RF TX safeguards."""
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from aprs_features import encode_ui_packet
from aprs_protocol import decode_ax25
from aprs_service import APRSService
from service_config import ServiceConfig
from web_panel import WebPanel


class TNCServiceWebTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.config=ServiceConfig(Path(self.temp.name)/'config.json').load_or_create()
        self.service=APRSService(self.config)
        self.web=WebPanel(self.service.state,operator=self.service,
            viewer_token=self.config.secrets['viewer_token'],
            admin_token=self.config.secrets['admin_token'])
        self.port=self.web.start(lan=True,port=0)
        self.base='http://127.0.0.1:'+str(self.port)
        self.admin='?admin='+self.config.secrets['admin_token']

    def tearDown(self):
        self.web.close()
        if self.service.tcp_hub:
            self.service.tcp_hub.close()
        self.service.archive.close()
        self.service.messages.close()
        self.service.journal.close()
        self.temp.cleanup()

    def test_api_auth_and_rx_history(self):
        p=decode_ax25(encode_ui_packet("OK1ABC-7","APRS","",
                        "!4944.40N/01322.20E>test"))
        self.service._on_frame(p)
        with self.assertRaises(HTTPError) as unauthorized:
            urlopen(self.base+'/api/archive')
        self.assertEqual(unauthorized.exception.code,403)
        with urlopen(self.base+'/api/archive'+self.admin) as response:
            result=json.load(response)
            self.assertEqual(result['summary']['packets'],1)
            self.assertEqual(result['packets'][0]['source'],'OK1ABC-7')
        with urlopen(self.base+'/api/archive/positions'+self.admin+'&source=OK1ABC-7') as response:
            self.assertEqual(len(json.load(response)['positions']),1)
        with urlopen(self.base+'/api/tnc'+self.admin) as response:
            self.assertFalse(json.load(response)['server']['running'])
        with urlopen(self.base+'/api/weather'+self.admin) as response:
            self.assertEqual(json.load(response)['records'],[])

    def test_tcp_tx_never_turns_on_from_saved_settings(self):
        self.config.update({'tnc':{'kiss_server_enabled':True,'kiss_server_port':49152}})
        self.service._start_tnc_hub()
        try:
            self.assertFalse(self.service.tnc_snapshot()['tx_permission'])
            self.assertTrue(self.service.tnc_snapshot()['server']['rx_only'])
            with self.assertRaises(ValueError):
                self.service._execute('tnc_server_tx',{'enabled':True})
            self.assertTrue(self.service.tnc_snapshot()['server']['rx_only'])
            self.service._disconnect_reader()
            self.assertFalse(self.service.tnc_snapshot()['tx_permission'])
        finally:
            self.service.tcp_hub.close()
            self.service.tcp_hub=None

    def test_service_receives_real_weather_packet(self):
        p=decode_ax25(encode_ui_packet("OK1WX-1","APRS","",
                        "!4944.40N/01322.20E_11092215c090s005g010t032h00b10132"))
        self.service._on_frame(p)
        self.assertEqual(self.service.archive.summary()['weather'],1)
        self.assertEqual(self.service.latest_weather['OK1WX-1']['humidity_pct'],100)
        self.assertEqual(self.service.latest_weather['OK1WX-1']['temperature_c'],0)


if __name__ == '__main__':
    unittest.main()
