"""DIGI RF beacon and RF telemetry regression tests (USB simulated, no real RF)."""
from __future__ import annotations

import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aprs_features import encode_kiss_data, encode_ui_packet
from aprs_protocol import KissDecoder, decode_ax25
from aprs_serial import SerialReader
from aprs_service import APRSService
from service_config import ServiceConfig


class StubReader:
    def __init__(self):
        self.sent=[]
        self.digi_allowed=threading.Event()
        self.accept=True

    def send(self, data, category='manual'):
        if not self.accept:
            return False
        self.sent.append((data,category))
        return True


def decoded(frame):
    frames=KissDecoder().feed(frame)
    if len(frames)!=1:
        raise AssertionError(f'Expected one KISS frame, got {len(frames)}')
    return decode_ax25(frames[0][1:])


class DIGIRFBeaconTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.conf=ServiceConfig(Path(self.tmp.name)/'config.json').load_or_create()
        self.svc=APRSService(self.conf)
        self.reader=StubReader()
        self.svc.reader=self.reader
        self.svc.radio_ready=True
        self.conf.update({'position':{'latitude':49.72,'longitude':13.29}})

    def tearDown(self):
        self.svc.messages.close()
        self.svc.journal.close()
        self.tmp.cleanup()

    def enable(self, **updates):
        opts={'beacon_enabled':True,'beacon_transport':'rf',
              'beacon_rf_path':'DIRECT','beacon_interval':30}
        opts.update(updates)
        self.conf.update({'digi':opts})
        self.svc._enable_digi()

    def test_old_aprsis_beacon_does_not_transmit_rf(self):
        self.conf.update({'digi':{'beacon_enabled':True}})
        self.svc._enable_digi()
        self.svc._telemetry_tick()
        self.assertFalse(self.reader.sent)
        self.assertEqual(self.conf.data['digi']['beacon_transport'],'is')

    def test_beacon_is_queued_immediately_and_periodically_without_aprsis(self):
        self.enable(beacon_rf_path='WIDE1-1',beacon_comment='OK5TVR TEST DIGI')
        self.assertIsNone(self.svc.igate_client)
        self.svc._telemetry_tick()
        self.assertEqual(len(self.reader.sent),1)
        frame,category=self.reader.sent[0]
        self.assertEqual(category,'digi_beacon_rf')
        pkt=decoded(frame)
        self.assertEqual(pkt.source,'OK5TVR-3')
        self.assertEqual(pkt.destination,'APRS')
        self.assertEqual(pkt.path,'WIDE1-1')
        self.assertTrue(pkt.raw_info.startswith(b'!'))
        self.assertIn(b'OK5TVR TEST DIGI',pkt.raw_info)
        self.assertEqual(pkt.latitude,49.72)
        self.assertAlmostEqual(pkt.longitude,13.29,places=3)
        self.assertNotIn(b'TCPIP',frame)
        for _ in range(4):
            self.svc._telemetry_tick()
        self.assertEqual(len(self.reader.sent),1)
        self.svc.digi_last_rf_position=time.monotonic()-30*60-1
        self.svc.rf_telemetry_next_tx=0  # simulated elapsed RF cooldown
        self.svc._telemetry_tick()
        self.assertEqual(len(self.reader.sent),2)
        self.svc._disable_digi()
        self.svc.digi_last_rf_position=float('-inf')
        self.svc._telemetry_tick()
        self.assertEqual(len(self.reader.sent),2)

    def test_no_beacon_if_serial_unavailable_queue_full_or_digi_off(self):
        self.enable()
        self.reader.accept=False
        self.svc._telemetry_tick()
        self.assertFalse(self.reader.sent)
        self.reader.accept=True
        self.svc._telemetry_tick()
        self.assertEqual(len(self.reader.sent),1)
        self.svc.radio_ready=False
        self.svc.digi_last_rf_position=float('-inf')
        self.svc._telemetry_tick()
        self.assertEqual(len(self.reader.sent),1)

    def test_metadata_burst_has_priority_over_position_beacon(self):
        self.enable()
        self.svc.rf_telemetry_pending.append(b'KISS-not-sent-yet')
        self.svc.rf_telemetry_next_tx=float('inf')
        self.svc._telemetry_tick()
        self.assertFalse(self.reader.sent)
        self.svc.rf_telemetry_pending.clear()
        self.svc.rf_telemetry_next_tx=0  # metadata TX cooldown elapsed
        self.svc._telemetry_tick()
        self.assertEqual(self.reader.sent[0][1],'digi_beacon_rf')

    def test_rf_beacon_does_not_require_aprsis_login_same_base_callsign(self):
        self.conf.update({'digi':{'call':'OK1XYZ-3', 'beacon_enabled':True,
                                  'beacon_transport':'rf'}})
        self.svc._enable_digi()
        self.svc._telemetry_tick()
        self.assertEqual(decoded(self.reader.sent[0][0]).source,'OK1XYZ-3')

    def test_explicit_confirmation_for_rf_beacon(self):
        with self.assertRaisesRegex(ValueError,'explicit confirmation'):
            self.svc._execute('save', {'config':{'digi':{
                'beacon_enabled':True,'beacon_transport':'rf'}}})
        self.assertFalse(self.conf.data['digi']['beacon_enabled'])
        self.svc._execute('save', {'config':{'digi':{
            'beacon_enabled':True,'beacon_transport':'rf'}},
            'confirm_rf_beacon':True})
        self.assertTrue(self.conf.data['digi']['beacon_enabled'])
        self.assertFalse(self.svc.digi.enabled)  # no implicit RF activation after save
        # A later unrelated message-settings save must not need RF consent again.
        self.svc._execute('save', {'config':{'messages':{'retry_seconds':60}}})

    def test_beacon_and_telemetry_keep_12s_gap(self):
        self.enable()
        self.conf.update({'digi':{'telemetry_enabled':True,'telemetry_transport':'rf'}})
        self.svc._telemetry_tick()  # beacon on activation
        self.assertEqual([c for _,c in self.reader.sent],['digi_beacon_rf'])
        self.assertEqual(self.svc._telemetry_send(force_metadata=True),5)
        self.svc._rf_telemetry_tick()  # no immediately adjacent T# frame
        self.assertEqual(len(self.reader.sent),1)
        self.svc.rf_telemetry_next_tx=0  # after 12-second gap
        self.svc._rf_telemetry_tick()
        self.assertEqual([c for _,c in self.reader.sent],['digi_beacon_rf','telemetry_rf'])

    def test_rf_telemetry_automatic_interval_without_aprsis(self):
        self.conf.update({'digi':{'telemetry_enabled':True,'telemetry_transport':'rf'}})
        self.svc._enable_digi()
        self.svc.telemetry_next=0  # report interval became due
        self.svc._telemetry_tick()  # schedules the five frames
        self.assertEqual(len(self.svc.rf_telemetry_pending),5)
        self.svc._telemetry_tick()  # next scheduler pass writes first frame to KISS queue
        self.assertEqual(self.reader.sent[0][1], 'telemetry_rf')

    def test_rf_telemetry_uses_usb_kiss_and_requires_enabled_digi(self):
        self.conf.update({'digi':{'telemetry_enabled':True,'telemetry_transport':'rf',
                                  'telemetry_rf_path':'DIRECT'}})
        self.assertEqual(self.svc._telemetry_send(force_metadata=True),0)
        self.svc._enable_digi()
        self.assertEqual(self.svc._telemetry_send(force_metadata=True),5)
        for _ in range(5):
            self.svc.rf_telemetry_next_tx=0
            self.svc._rf_telemetry_tick()
        self.assertEqual(len(self.reader.sent),5)
        packets=[decoded(v[0]) for v in self.reader.sent]
        self.assertTrue(all(p.source=='OK5TVR-3' and p.path=='' for p in packets))
        self.assertTrue(all(v[1]=='telemetry_rf' for v in self.reader.sent))
        self.assertTrue(packets[-1].raw_info.startswith(b'T#'))
        self.svc._disable_digi()
        self.assertFalse(self.svc.rf_telemetry_pending)


class MinimalFakeUSB:
    writes=queue.Queue()
    def __init__(self,*args,**kwargs):
        self.dtr=False
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def write(self,data):
        self.writes.put(data)
        return len(data)
    def flush(self): pass
    def read(self,n):
        time.sleep(.02)
        return b''


class RFBeaconSerialGuardTests(unittest.TestCase):
    def test_serial_writes_beacon_with_digi_permission(self):
        MinimalFakeUSB.writes=queue.Queue()
        events=queue.Queue()
        stopper=threading.Event()
        reader=SerialReader('MOCKUSB',115200,events,stopper,9)
        pkt=encode_kiss_data(encode_ui_packet('OK5TVR-3','APRS','WIDE1-1',
                           '!4943.20N/01317.40E#OK5TVR DIGI'))
        reader.digi_allowed.set()
        with patch('aprs_serial.serial',SimpleNamespace(Serial=MinimalFakeUSB)):
            self.assertTrue(reader.send(pkt,category='digi_beacon_rf'))
            reader.start()
            deadline=time.monotonic()+2
            while time.monotonic()<deadline and MinimalFakeUSB.writes.empty():
                time.sleep(.02)
            self.assertFalse(MinimalFakeUSB.writes.empty())
            raw=MinimalFakeUSB.writes.get_nowait()
            self.assertEqual(raw,pkt)
            self.assertEqual(decoded(raw).source,'OK5TVR-3')
            self.assertTrue(any(event[1]=='tx_written' and
                                event[2]['category']=='digi_beacon_rf'
                                for event in list(events.queue)))
            stopper.set();reader.join(timeout=2)
            self.assertFalse(reader.is_alive())

    def test_serial_drops_pending_beacon_when_digi_disabled(self):
        MinimalFakeUSB.writes=queue.Queue()
        events=queue.Queue()
        stopper=threading.Event()
        reader=SerialReader('MOCKUSB',115200,events,stopper,8)
        pkt=encode_kiss_data(encode_ui_packet('OK5TVR-3','APRS','',
             '!4943.20N1 01317.40E#test'.replace('1 ', '1')))
        with patch('aprs_serial.serial',SimpleNamespace(Serial=MinimalFakeUSB)):
            # Queue before starting thread, without enabling DIGI.
            self.assertTrue(reader.send(pkt,category='digi_beacon_rf'))
            reader.start()
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                if any(event[1]=='tx_cancelled' for event in list(events.queue)):
                    break
                time.sleep(.02)
            else:
                self.fail('Expected TX cancellation when DIGI is off')
            self.assertTrue(MinimalFakeUSB.writes.empty())
            stopper.set();reader.join(timeout=2)
            self.assertFalse(reader.is_alive())

if __name__=='__main__':
    unittest.main()
