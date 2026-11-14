"""v2.3 integration tests: one real APRS service / authenticated read-only web."""
from __future__ import annotations

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


class CommandCenterV23ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.conf=ServiceConfig(Path(self.tmp.name)/'config.json').load_or_create()
        self.service=APRSService(self.conf)
        self.web=WebPanel(self.service.state,operator=self.service,
                          viewer_token=self.conf.secrets['viewer_token'],
                          admin_token=self.conf.secrets['admin_token'])
        self.port=self.web.start(lan=True,port=0)
        self.base='http://127.0.0.1:'+str(self.port)
        self.admin='?admin='+self.conf.secrets['admin_token']

    def tearDown(self):
        self.web.close()
        self.service.secondary.close()
        self.service.alerts.close()
        self.service.archive.close()
        self.service.messages.close()
        self.service.journal.close()
        self.tmp.cleanup()

    def test_heard_and_alert_api_are_admin_only(self):
        p=decode_ax25(encode_ui_packet('OK1ABC-7','APRS','',
            '!4944.40N/01322.20E>receiver test'))
        self.service._on_frame(p)
        for path in ('/api/heard','/api/alerts','/api/tx-scheduler'):
            with self.subTest(path=path),self.assertRaises(HTTPError) as unauth:
                urlopen(self.base+path)
            self.assertEqual(unauth.exception.code,403)
        with urlopen(self.base+'/api/heard'+self.admin) as response:
            rows=json.load(response)['stations']
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['receiver'],'primary')
            self.assertEqual(rows[0]['source'],'OK1ABC-7')
            self.assertEqual(rows[0]['direct_packets'],1)
        with urlopen(self.base+'/api/tx-scheduler'+self.admin) as response:
            tx=json.load(response)
            self.assertEqual(tx['max_pending'],12)
        with urlopen(self.base+'/api/alerts'+self.admin) as response:
            self.assertTrue(json.load(response)['enabled'])

    def test_receive_only_secondary_does_not_forward_to_igate(self):
        other=decode_ax25(encode_ui_packet('OK1LOR-1','APRS','',
            '!4944.40N/01322.20E>LoRa'))
        self.service._on_secondary_frame(other,'lora433')
        self.assertEqual(self.service.stats['secondary_rx'],1)
        self.assertEqual(self.service.archive.heard(receiver='lora433')[0]['receiver'],'lora433')
        self.assertEqual(self.service.state.snapshot()['stations'][0]['receivers'],['lora433'])
        self.assertIsNone(self.service.igate_client)
        self.assertFalse(self.service.isrf.active)

    def test_runtime_alert_update_does_not_enable_rf(self):
        rules=dict(self.conf.data['alerts'])
        rules['watch_calls']=['OK1ABC-7']
        self.service._execute('alerts_save',{'rules':rules})
        p=decode_ax25(encode_ui_packet('OK1ABC-7','APRS','','>QRV'))
        self.service._on_frame(p)
        self.assertEqual(self.service.alerts.snapshot()['events'][0]['code'],'watched_station')
        self.assertFalse(self.service.want_digi)
        self.assertFalse(self.service.isrf.active)

    def test_message_unread_and_bulletin_marking(self):
        message=decode_ax25(encode_ui_packet('OK1ABC-7','APRS','',
            ':OK5TVR-10:Hello'))
        self.service._on_frame(message)
        self.assertEqual(self.service.messages_snapshot()['unread'],1)
        message_id=self.service.messages_snapshot()['inbox'][0]['id']
        self.service._execute('message_read',{'kind':'message','id':message_id})
        self.assertEqual(self.service.messages_snapshot()['unread'],0)
        bulletin=decode_ax25(encode_ui_packet('OK1ABC-7','APRS','',
            ':BLN1     :APRS weekend'))
        self.service._on_frame(bulletin)
        self.assertEqual(self.service.messages_snapshot()['unread_bulletins'],1)
        self.service._execute('message_blocklist',{'calls':['OK1ABC-7']})
        self.assertEqual(self.service.messages_snapshot()['blocked_senders'],['OK1ABC-7'])


if __name__=='__main__':
    unittest.main()
