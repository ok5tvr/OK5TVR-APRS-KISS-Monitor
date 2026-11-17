"""Concurrent AX.25 PBBS links share RF capacity but never sequence or mail state."""
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from aprs_bbs import AX25PBBS
from aprs_serial import SerialReader
from aprs_tcp import TCPKissReader
from service_config import validate_config
from test_bbs_v24 import Clock, bbs_cfg, rx

A='OK1ABC-7';B='OK2XYZ-7';C='OK3XYZ-7'


class MultiClientTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.clock=Clock()
        self.bbs=AX25PBBS(Path(self.temp.name)/'bbs.sqlite3',bbs_cfg(max_clients=2),self.clock)
        self.out=[];self.send=lambda data,category:self.out.append((data,category)) or True
        self.bbs.start()
    def tearDown(self):self.bbs.close();self.temp.cleanup()
    def connect(self,call):
        self.bbs.on_frame(rx(src=call),self.send)
        category=self.out[-1][1];self.bbs.on_tx_written(category)
        return category
    def test_independent_ack_sequences_and_input_drafts(self):
        self.connect(A);self.connect(B)
        self.assertEqual(self.bbs.snapshot()['client_count'],2)
        self.bbs.tick(self.send)
        for _,category in self.out:self.bbs.on_tx_written(category)
        a=self.bbs.sessions[A];b=self.bbs.sessions[B]
        self.assertIsNotNone(a.unacked);self.assertIsNotNone(b.unacked)
        b_pending=b.unacked
        self.bbs.on_frame(rx(src=A,control=0x21),self.send) # N(R)=1 acknowledges A only
        self.assertIsNone(a.unacked);self.assertIs(b.unacked,b_pending)
        self.bbs.on_frame(rx(src=A,control=0x20,text=b'\xF0SB\rTitle A\rBody A\r'),self.send)
        self.bbs.on_frame(rx(src=B,control=0x00,text=b'\xF0SP OK4XYZ-7\rTitle B\rBody B\r'),self.send)
        self.assertEqual(a.subject,'Title A');self.assertEqual(b.subject,'Title B')
        self.assertNotEqual(a.body,b.body);self.assertEqual(a.vr,1);self.assertEqual(b.vr,1)
        self.bbs.on_frame(rx(src=A,control=0x22,text=b'\xF0/EX\r'),self.send)
        self.bbs.on_frame(rx(src=B,control=0x22,text=b'\xF0/EX\r'),self.send)
        _,mail=self.bbs.store.admin_list()
        self.assertEqual({item['sender'] for item in mail},{A,B})
        self.assertEqual({(item['sender'],item['subject']) for item in mail},{(A,'Title A'),(B,'Title B')})
        # B cannot read A's private mailbox via its own connection.
        private=self.bbs.store.post(A,'OK4XYZ-7','Secret','For recipient only')
        b.output.clear()
        self.bbs.on_frame(rx(src=B,control=0x24,text=b'\xF0'+('R '+str(private)+'\r').encode()),self.send)
        self.assertIn(b'Message not available',b.output)
        self.assertNotIn(b'For recipient only',b.output)

    def test_capacity_disconnect_reset_and_late_callback_do_not_disturb_other_client(self):
        old_a=self.connect(A);b_category=self.connect(B)
        self.bbs.on_frame(rx(src=C),self.send)
        self.assertEqual(set(self.bbs.sessions),{A,B});self.assertTrue(self.out[-1][1].startswith('bbs_reply:'))
        self.bbs.on_frame(rx(src=A,control=0x53),self.send)
        final=self.out[-1][1]
        self.assertNotIn(A,self.bbs.sessions);self.assertTrue(self.bbs.tx_valid(final))
        self.assertFalse(self.bbs.tx_valid(old_a));self.assertTrue(self.bbs.tx_valid(b_category))
        self.connect(C);self.assertEqual(set(self.bbs.sessions),{B,C})
        old_b=self.bbs.sessions[B];old_b.output.clear()
        self.connect(B);new_b=self.bbs.sessions[B]
        self.assertIsNot(new_b,old_b);self.assertFalse(self.bbs.tx_valid(b_category))
        new_b.waiting_ua=True;self.bbs.on_tx_written(b_category);self.assertTrue(new_b.waiting_ua)
        self.bbs.on_frame(rx(src=C,control=0x53),self.send)
        self.connect(A);self.assertFalse(self.bbs.tx_valid(final)) # stale DISC reply must not enter the new A session
        self.bbs.stop();self.assertFalse(self.bbs.tx_valid(final));self.assertFalse(self.bbs.sessions)

    def test_timeout_and_selected_sysop_disconnect_are_per_client(self):
        self.connect(A);self.connect(B)
        self.bbs.sessions[A].last=self.clock()-181
        self.bbs.sessions[B].last=self.clock()
        self.bbs.tick(self.send)
        self.assertEqual(set(self.bbs.sessions),{B})
        self.connect(C);self.bbs.request_disconnect(B)
        self.assertTrue(self.bbs.sessions[B].closing);self.assertFalse(self.bbs.sessions[C].closing)
        with self.assertRaises(ValueError):self.bbs.request_disconnect(A)

    def test_shared_rate_limit_and_link_specific_transport_permission(self):
        ca=self.connect(A);cb=self.connect(B)
        self.bbs.config['max_tx_per_minute']=3
        self.bbs.tick(self.send)
        self.assertEqual(len(self.out),3)
        self.assertEqual(len(self.bbs.tx_times),3) # not 3 per station
        for reader in (SerialReader('FAKE',115200,queue.Queue(),threading.Event(),1),TCPKissReader('localhost',8001,queue.Queue(),threading.Event(),1)):
            reader.bbs_allowed.set();reader.connected=True;reader.bbs_valid=self.bbs.tx_valid
            self.assertTrue(reader.send(b'x',ca));self.assertTrue(reader.send(b'x',cb))
            self.bbs.on_frame(rx(src=A,control=0x53),self.send)
            self.assertFalse(reader.send(b'x',ca));self.assertTrue(reader.send(b'x',cb))
            # Reintroduce A for the next transport.
            self.clock.step(61);ca=self.connect(A)

    def test_setting_bounds_and_migration(self):
        self.assertEqual(validate_config({})['bbs']['max_clients'],5)
        self.assertEqual(validate_config({'bbs':{'max_clients':1}})['bbs']['max_clients'],1)
        for value in (0,11,True,'5'):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_config({'bbs':{'max_clients':value}})

class MultiClientServiceTests(unittest.TestCase):
    def test_selected_disconnect_and_snapshot_via_service(self):
        from aprs_service import APRSService
        from service_config import ServiceConfig
        with tempfile.TemporaryDirectory() as directory:
            config=ServiceConfig(Path(directory)/'config.json').load_or_create()
            config.update({'station':{'mode':'bbs'},'bbs':{'max_clients':2}})
            service=APRSService(config)
            try:
                service.reader=SerialReader('FAKE',115200,queue.Queue(),threading.Event(),1)
                service.radio_ready=True
                service._execute('bbs_on',{'confirm':True,'confirm_channel':True})
                service.bbs.on_frame(rx(src=A),service._bbs_send)
                service.bbs.on_frame(rx(src=B),service._bbs_send)
                self.assertEqual(service.bbs_snapshot()['client_count'],2)
                self.assertEqual(service.bbs_snapshot()['max_clients'],2)
                service._execute('bbs_disconnect',{'remote':B,'confirm':True})
                self.assertTrue(service.bbs.sessions[B].closing)
                self.assertFalse(service.bbs.sessions[A].closing)
                service._execute('bbs_off',{})
                self.assertFalse(service.bbs.sessions)
                self.assertFalse(service.reader.bbs_allowed.is_set())
            finally:
                for name in ('bbs','secondary','alerts','archive','messages','journal'):getattr(service,name).close()
