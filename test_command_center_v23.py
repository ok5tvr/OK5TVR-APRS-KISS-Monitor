"""v2.3 regression tests for RF scheduling, multiple TNC, heard map and alerts."""
import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path

from aprs_alerts import AlertEngine
from aprs_archive import APRSArchive
from aprs_features import encode_ui_packet
from aprs_messages import MessageManager
from aprs_protocol import decode_ax25
from aprs_rf_scheduler import RFOutputScheduler
from aprs_secondary_tnc import SecondaryTNCManager, ReadOnlySerial, ReadOnlyTCP
from service_config import ServiceConfig, validate_config


class Clock:
    def __init__(self):
        self.t=1000.
    def __call__(self):
        return self.t
    def jump(self,sec):
        self.t+=sec


def packet(call='OK1ABC-7',data='!4944.40N/01322.20E>TEST',receiver='primary'):
    result=decode_ax25(encode_ui_packet(call,'APRS','',data))
    result.receiver=receiver
    return result


class RFQueueV23Tests(unittest.TestCase):
    def test_priorities_min_gap_and_global_rate(self):
        clk=Clock()
        tx=RFOutputScheduler(max_pending=8,min_gap_s=2,max_per_minute=2,clock=clk)
        tx.put_nowait((b'DIGI','digi'))
        tx.put_nowait((b'TELEM','telemetry_rf'))
        tx.put_nowait((b'ACK','msgack:5'))
        self.assertEqual(tx.get_nowait(),(b'ACK','msgack:5'))
        with self.assertRaises(queue.Empty):tx.get_nowait()
        clk.jump(2)
        self.assertEqual(tx.get_nowait(),(b'DIGI','digi'))
        clk.jump(2)
        with self.assertRaises(queue.Empty):tx.get_nowait()
        clk.jump(60)
        self.assertEqual(tx.get_nowait(),(b'TELEM','telemetry_rf'))
        self.assertEqual(tx.snapshot()['pending'],0)

    def test_bounds_and_expiry(self):
        clk=Clock()
        tx=RFOutputScheduler(max_pending=2,min_gap_s=0,max_per_minute=30,clock=clk)
        tx.put_nowait((b'A','digi'))
        tx.put_nowait((b'B','digi'))
        with self.assertRaises(queue.Full):tx.put_nowait((b'C','digi'))
        self.assertEqual(tx.snapshot()['rejected_full'],1)
        clk.jump(95)
        with self.assertRaises(queue.Empty):tx.get_nowait()
        self.assertEqual(tx.snapshot()['expired'],2)

    def test_invalid_config_rejected(self):
        for setting in [{'min_gap_s':-1},{'max_per_minute':0},
                        {'max_pending':33},{'min_gap_s':20}]:
            with self.subTest(setting=setting),self.assertRaises(ValueError):
                validate_config({'tx_scheduler':setting})


class SecondaryV23Tests(unittest.TestCase):
    @staticmethod
    def device():
        return {'id':'lora433','enabled':True,'transport':'tcp',
                'host':'127.0.0.1','port':8999,'serial_port':'','baud':115200}

    def test_isolated_rx_only_and_port_validation(self):
        item=self.device()
        value=validate_config({'secondary_tncs':{'devices':[item]}})
        self.assertEqual(value['secondary_tncs']['devices'][0]['id'],'lora433')
        self.assertFalse(ReadOnlyTCP('127.0.0.1',8999,queue.Queue(),threading.Event(),1).send(b'C0'))
        self.assertFalse(ReadOnlySerial('COM7',115200,queue.Queue(),threading.Event(),1).send(b'C0'))
        for bad in [
            {'secondary_tncs':{'devices':[item,item]}},
            {'secondary_tncs':{'devices':[{**item,'id':'Bad Name'}]}},
            {'secondary_tncs':{'devices':[{**item,'transport':'weird'}]}},
            {'secondary_tncs':{'devices':[{**item,'transport':'serial','serial_port':''}]}},
        ]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):validate_config(bad)

    def test_receiver_events_do_not_use_primary_send(self):
        item=self.device()
        manager=SecondaryTNCManager([item])
        class FakeReader:
            session=1234
            def join(self,timeout=None):pass
        manager.entries['lora433']['reader']=FakeReader()
        manager.entries['lora433']['stop']=threading.Event()
        manager.sessions[1234]='lora433'
        seen=[]
        manager.events.put((1234,'connected','127.0.0.1:8999'))
        manager.events.put((1234,'frame',packet()))
        try:
            manager.tick(lambda p,receiver:seen.append((p.source,p.receiver,receiver)))
            self.assertEqual(seen,[('OK1ABC-7','lora433','lora433')])
            self.assertEqual(manager.snapshot()[0]['rx'],1)
            self.assertTrue(manager.snapshot()[0]['rx_only'])
        finally:
            manager.close()


class ArchiveHeardV23Tests(unittest.TestCase):
    def test_receiver_schema_new_and_old_archive_upgrade(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'aprs.sqlite3'
            with sqlite3.connect(path) as db:
                db.execute('''CREATE TABLE packets (
                    id INTEGER PRIMARY KEY, received_at TEXT,source TEXT,
                    destination TEXT,path TEXT,kind TEXT,summary TEXT,
                    lat REAL,lon REAL,direct INTEGER,ax25_hex TEXT,weather INTEGER)''')
            archive=APRSArchive(path,max_rows=1000)
            try:
                archive.add(packet(receiver='lora433'))
                archive.add(packet(call='OK1XYZ-8'))
                rows=archive.heard(minutes=1440)
                self.assertEqual({row['receiver'] for row in rows},{'primary','lora433'})
                self.assertEqual(sum(row['direct_packets'] for row in rows),2)
                self.assertEqual(len(archive.heard(receiver='lora433')),1)
                self.assertEqual(archive.packets()[0]['receiver'],'primary')
            finally:
                archive.close()


class MessagesV23Tests(unittest.TestCase):
    def test_bulletins_unread_and_blocked_senders(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr=MessageManager(Path(tmp)/'messages.sqlite3','OK5TVR-10',
                               blocked_senders=['OK1BAD-7'])
            try:
                text=':BLN1     :Public bulletin'
                msg=mgr.receive(packet(data=text),True)
                self.assertEqual(msg['kind'],'bulletin')
                view=mgr.snapshot()
                self.assertEqual(view['unread_bulletins'],1)
                self.assertEqual(len(view['bulletins']),1)
                mgr.mark_read('bulletin',view['bulletins'][0]['id'])
                self.assertEqual(mgr.snapshot()['unread_bulletins'],0)
                blocked=mgr.receive(packet('OK1BAD-7',':OK5TVR-10:blocked'),True)
                self.assertIsNone(blocked)
                m=mgr.receive(packet('OK1GUD-7',':OK5TVR-10:hello'),True)
                self.assertEqual(m['kind'],'message')
                self.assertEqual(mgr.snapshot()['unread'],1)
                self.assertTrue(mgr.mark_read('message',m['inbox_id'])['found'])
                self.assertEqual(mgr.snapshot()['unread'],0)
                self.assertEqual(mgr.snapshot()['conversations'][0]['callsign'],'OK1GUD-7')
            finally:mgr.close()


class AlertsV23Tests(unittest.TestCase):
    def test_deduplicate_alerts_and_weather(self):
        clk=Clock()
        c=validate_config({'alerts':{'enabled':True,'offline_seconds':60,
                         'no_rf_minutes':15,'watch_calls':['OK1ABC-7'],
                         'weather_temp_high':30}})['alerts']
        engine=AlertEngine(c,clock=clk)
        try:
            engine.on_packet(packet())
            engine.on_packet(packet())
            self.assertEqual(engine.snapshot()['latest_id'],1)
            engine.on_packet(packet(),{'temperature_c':35})
            self.assertEqual(engine.snapshot()['latest_id'],2)
            engine.tick(uptime=100,radio_connected=False,last_rf_at=None,
                        igate_online=False,igate_enabled=True)
            self.assertEqual(engine.snapshot()['latest_id'],4)
            self.assertEqual(len(engine.snapshot()['events']),4)
        finally:engine.close()


if __name__ == '__main__':
    unittest.main()
