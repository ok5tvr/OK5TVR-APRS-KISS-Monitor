"""Tests of AX.25 modulo-8 PBBS over KISS, without accessing radio hardware."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from aprs_bbs import AX25PBBS, validate_bbs_config
from aprs_features import address_bytes
from aprs_protocol import KissDecoder, decode_ax25
from aprs_service import APRSService
from service_config import ServiceConfig, validate_config
from web_panel import WebPanel


def bbs_cfg(**kwargs):
    result = dict(call='OK5TVR-8',welcome='Test PBBS',max_messages=100,
                  idle_seconds=180,max_tx_per_minute=24,allow_posts=True)
    result.update(kwargs)
    return validate_bbs_config(result,'OK5TVR-10','OK5TVR-3')


def rx(src='OK1ABC-7', dst='OK5TVR-8', control=0x3F, text=b'', path=''):
    from aprs_features import address_bytes
    addresses=[address_bytes(dst),address_bytes(src,last=not bool(path))]
    if path:
        addresses.append(address_bytes(path,last=True))
    content=b''.join(addresses)+bytes([control])+text
    return decode_ax25(content)


class Clock:
    def __init__(self):self.current=1000.
    def __call__(self):return self.current
    def step(self,n):self.current+=n


class PbbsEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.clock=Clock()
        self.pbbs=AX25PBBS(Path(self.tmp.name)/'bbs.sqlite3',bbs_cfg(),clock=self.clock)
        self.out=[]
        self.send=lambda payload,category:(self.out.append((payload,category)) or True)

    def tearDown(self):
        self.pbbs.close()
        self.tmp.cleanup()

    def parsed_output(self,index=-1):
        data=KissDecoder().feed(self.out[index][0])
        self.assertEqual(len(data),1)
        return decode_ax25(data[0][1:])

    def connect(self):
        self.pbbs.start()
        self.assertTrue(self.pbbs.on_frame(rx(),self.send))
        self.assertEqual(len(self.out),1)
        self.assertEqual(self.parsed_output().control,0x73)
        self.assertEqual(self.parsed_output().source,'OK5TVR-8')
        self.assertEqual(self.parsed_output().destination,'OK1ABC-7')
        self.pbbs.on_tx_written(self.out[-1][1])
        self.pbbs.tick(self.send)
        self.assertGreaterEqual(len(self.out),2)
        self.assertEqual(self.parsed_output().control&1,0)  # AX.25 I
        self.assertIn(b'PBBS',self.parsed_output().raw_info)

    def test_default_off_and_separate_ssid_required(self):
        self.assertFalse(self.pbbs.active)
        self.assertFalse(self.pbbs.on_frame(rx(),self.send))
        self.assertEqual(len(self.out),0)
        self.assertEqual(validate_config({})['bbs']['call'],'')
        for bad in [dict(call='OK5TVR-10'),dict(call='OK5TVR-3'),
                    dict(call='OK1OTH-8'),dict(call='OK5TVR-17'),
                    dict(max_tx_per_minute=0),dict(idle_seconds=5),
                    dict(welcome='Hello\nworld')]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):bbs_cfg(**bad)

    def test_connect_and_no_second_station_or_via(self):
        self.connect()
        self.assertTrue(self.pbbs.on_frame(rx(src='OK2XYZ-7'),self.send))
        self.assertEqual(self.parsed_output().control,0x1F)
        self.assertTrue(self.pbbs.on_frame(rx(src='OK2XYZ-7',path='WIDE1-1'),self.send))
        self.assertEqual(self.pbbs.snapshot()['remote'],'OK1ABC-7')
        self.pbbs.stop()
        self.assertFalse(self.pbbs.active)
        self.assertFalse(self.pbbs.on_frame(rx(),self.send))

    def test_stop_and_wait_ack_and_help_request(self):
        self.connect()
        current=len(self.out)
        # User acknowledges first I (N(R)=1) and sends command H as I.
        incoming=rx(control=0x20, text=b'\xF0H\r')
        self.assertTrue(self.pbbs.on_frame(incoming,self.send))
        self.assertEqual(self.pbbs.session.vr,1)
        self.assertEqual(self.pbbs.counters['received_i'],1)
        self.assertEqual(self.parsed_output().control,0x21)  # RR N(R)=1
        self.pbbs.tick(self.send)
        self.assertEqual(self.parsed_output().control&1,0)
        # Repeated I-frame is acknowledged but not stored a second time.
        self.pbbs.on_frame(incoming,self.send)
        self.assertEqual(self.pbbs.counters['duplicate_i'],1)
        self.assertTrue(any('bbs_data:' in category for _,category in self.out[current:]))

    def test_sqlite_public_and_personal_mail_privacy(self):
        self.connect()
        self.pbbs._command('SB')
        self.pbbs._command('Public title')
        self.pbbs._command('Hello packet radio')
        self.pbbs._command('/EX')
        self.pbbs._command('SP OK1XYZ-9')
        self.pbbs._command('Private title')
        self.pbbs._command('For your eyes')
        self.pbbs._command('/EX')
        items=self.pbbs.store.list_for('OK1ABC-7')
        self.assertEqual(len(items),2)
        self.assertEqual(self.pbbs.store.list_for('OK2XYZ-7')[0]['recipient'],'ALL')
        private=[x for x in items if x['recipient']=='OK1XYZ-9'][0]
        self.assertIsNone(self.pbbs.store.read_for(private['id'],'OK2XYZ-7'))
        self.assertEqual(self.pbbs.store.read_for(private['id'],'OK1XYZ-9')['subject'],'Private title')
        self.assertEqual(self.pbbs.snapshot()['mail_count'],2)
        self.pbbs.close()
        self.pbbs=AX25PBBS(Path(self.tmp.name)/'bbs.sqlite3',bbs_cfg(),clock=self.clock)
        self.assertEqual(self.pbbs.snapshot()['mail_count'],2)

    def test_overlength_and_session_post_limit(self):
        self.connect()
        self.pbbs._command('SB')
        self.pbbs._command('Test')
        self.pbbs._command('x'*900)
        self.assertEqual(self.pbbs.session.stage,'body')
        self.pbbs._command('/EX')
        self.assertEqual(self.pbbs.snapshot()['mail_count'],0)
        for i in range(3):
            self.pbbs._command('SB')
            self.pbbs._command('title')
            self.pbbs._command('body')
            self.pbbs._command('/EX')
        self.assertEqual(self.pbbs.snapshot()['mail_count'],3)
        self.pbbs._command('SB')
        self.assertEqual(self.pbbs.session.stage,'command')

    def test_sabme_unsupported_and_malformed_calls(self):
        self.pbbs.start()
        self.assertTrue(self.pbbs.on_frame(rx(control=0x7F),self.send))
        self.assertEqual(self.parsed_output().control,0x1F)
        self.assertFalse(self.pbbs.on_frame(rx(dst='OK5TVR-10'),self.send))

    def test_disconnect_and_idle_timeout(self):
        self.connect()
        self.assertTrue(self.pbbs.on_frame(rx(control=0x53),self.send))
        self.assertEqual(self.parsed_output().control,0x73)
        self.assertFalse(self.pbbs.snapshot()['connected'])
        self.out.clear()  # fresh connection starts a new independent TX trace
        self.connect()
        self.clock.step(200)
        self.pbbs.tick(self.send)
        self.assertFalse(self.pbbs.snapshot()['connected'])


class FakeTNC:
    port='FAKE'
    def __init__(self):
        self.bbs_allowed=threading.Event()
        self.isrf_allowed=threading.Event()
        self.digi_allowed=threading.Event()
        self.bbs_epoch=-1
        self.tx=[]
    def send(self,payload,category='manual'):
        if category.startswith('bbs_') and (
                not self.bbs_allowed.is_set() or
                category.rsplit(':',1)[-1]!=str(self.bbs_epoch)):
            return False
        self.tx.append((payload,category))
        return True


class PbbsServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.conf=ServiceConfig(Path(self.tmp.name)/'config.json').load_or_create()
        self.conf.update({'station':{'mode':'bbs'}})
        self.service=APRSService(self.conf)
        self.tnc=FakeTNC()
        self.service.reader=self.tnc
        self.service.radio_ready=True

    def tearDown(self):
        self.service.bbs.close()
        self.service.secondary.close()
        self.service.alerts.close()
        self.service.archive.close()
        self.service.messages.close()
        self.service.journal.close()
        self.tmp.cleanup()

    def test_web_admin_auth_no_unintended_tx_and_revoke(self):
        web=WebPanel(self.service.state,operator=self.service,
            viewer_token=self.conf.secrets['viewer_token'],
            admin_token=self.conf.secrets['admin_token'])
        port=web.start(lan=True,port=0)
        root='http://127.0.0.1:'+str(port)
        try:
            for suffix in ('/api/bbs','/bbs'):
                with self.subTest(suffix=suffix),self.assertRaises(HTTPError) as x:
                    urlopen(root+suffix)
                self.assertEqual(x.exception.code,403)
            with urlopen(root+'/api/bbs?admin='+self.conf.secrets['admin_token']) as result:
                self.assertIn(b'"active": false',result.read())
            with urlopen(root+'/bbs?admin='+self.conf.secrets['admin_token']) as result:
                self.assertIn(b'Packet BBS',result.read())
        finally:web.close()
        self.service._execute('bbs_save',{'bbs':bbs_cfg()})
        self.assertFalse(self.service.bbs.active)
        self.assertFalse(self.tnc.bbs_allowed.is_set())
        with self.assertRaises(ValueError):
            self.service._execute('bbs_on',{'confirm':True})
        self.service._execute('bbs_on',{'confirm':True,'confirm_channel':True})
        self.assertTrue(self.tnc.bbs_allowed.is_set())
        self.service._on_frame(rx())
        self.assertEqual(self.service.bbs.snapshot()['remote'],'OK1ABC-7')
        self.assertEqual(len(self.tnc.tx),1)
        self.assertEqual(self.tnc.tx[0][1],f'bbs_link:{self.service.bbs.epoch}')
        self.service._execute('bbs_off',{})
        self.assertFalse(self.tnc.bbs_allowed.is_set())
        self.assertFalse(self.tnc.send(self.tnc.tx[0][0],category=self.tnc.tx[0][1]))
        self.assertFalse(self.service.bbs.snapshot()['connected'])

    def test_bbs_requires_no_aprs_digi_or_igate(self):
        self.service._execute('bbs_save',{'bbs':bbs_cfg()})
        self.service.digi.enabled=True
        with self.assertRaises(ValueError):
            self.service._execute('bbs_on',{'confirm':True,'confirm_channel':True})
        self.service.digi.enabled=False

    def test_bbs_does_not_autostart_from_persisted_config(self):
        self.service._execute('bbs_save',{'bbs':bbs_cfg()})
        fresh=ServiceConfig(self.conf.path).load_or_create()
        self.assertEqual(fresh.data['bbs']['call'],'OK5TVR-8')
        self.assertFalse(self.service.bbs.active)


if __name__=='__main__':
    unittest.main()
