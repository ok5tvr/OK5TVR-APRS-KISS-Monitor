"""Selective APRS-IS -> RF filter and AX.25 third-party regression tests.

All transmissions are intercepted: tests never connect to an RF radio.
"""
from __future__ import annotations

import queue
import socket
import threading
import time
import unittest
from dataclasses import dataclass
from types import SimpleNamespace

from aprs_features import APRSISClient, encode_ui_packet, igate_tnc2
from aprs_is_to_rf import (SelectiveISGate, parse_tnc2, third_party_kiss,
                            server_filter, validate_filter_config)
from aprs_protocol import KissDecoder, decode_ax25
from service_config import validate_config


class Clock:
    def __init__(self):
        self.now = 1000.
    def __call__(self):
        return self.now
    def advance(self, seconds):
        self.now += seconds


def config(**options):
    base = {'calls':['OK1SRC-7'], 'objects':['EVENT1'],
            'types':['message','position','object'],
            'rf_path':'', 'heard_minutes':30,
            'max_per_minute':2,'max_per_hour':8,
            'min_gap_seconds':15, 'duplicate_seconds':120}
    base.update(options)
    return validate_filter_config(base)


def incoming(source='OK1SRC-7',info='!4944.40N/01322.20E>Test',path='TCPIP*,qAC,T2TEST'):
    return f'{source}>APRS,{path}:{info}'


def message(target='OK1LOCAL-9', source='OK1SRC-7', body='Hello{1'):
    return incoming(source, f':{target:<9}:{body}')


class SelectiveIGateTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.gate = SelectiveISGate(config(), 'OK5TVR-10', clock=self.clock)
        self.frames = []

    def send(self, frame):
        self.frames.append(frame)
        return True

    def note_direct(self, call):
        packet = decode_ax25(encode_ui_packet(call,'APRS','','>QRV'))
        self.gate.note_rf(packet)

    def test_safe_defaults_and_reject_bad_rules(self):
        self.assertFalse(validate_config({})['is_to_rf']['calls'])
        self.assertEqual(validate_config({})['is_to_rf']['rf_path'],'')
        for args in [
            {'calls':['OK1*']}, {'calls':['OK1ABC-17']},
            {'objects':['EVENT*']}, {'rf_path':'WIDE2-2'},
            {'types':['message','command']}, {'max_per_minute':0},
            {'max_per_hour':0}, {'max_per_minute':7},
            {'duplicate_seconds':5}, {'min_gap_seconds':1}]:
            with self.subTest(args=args),self.assertRaises(ValueError):
                config(**args)
        self.assertIn('b/OK1SRC-7',server_filter(config()))
        self.assertIn('o/EVENT1',server_filter(config()))

    def test_ignores_full_internet_feed_until_explicitly_enabled(self):
        decision = self.gate.inspect(incoming())
        self.assertEqual(decision['reason'],'matched')
        did_send,reason = self.gate.process(incoming(),self.send,True,True)
        self.assertFalse(did_send)
        self.assertEqual(reason,'preview_only')
        self.assertEqual(self.frames,[])
        self.gate.start()
        self.assertTrue(self.gate.active)
        self.gate.stop()
        self.assertFalse(self.gate.active)

    def test_encoding_has_outer_gate_and_mandatory_tcpip_without_q(self):
        pkt = parse_tnc2(incoming())
        encoded = third_party_kiss(pkt,'OK5TVR-10','WIDE1-1')
        unpacked = KissDecoder().feed(encoded)
        self.assertEqual(len(unpacked),1)
        ax = decode_ax25(unpacked[0][1:])
        self.assertEqual(ax.source,'OK5TVR-10')
        self.assertEqual(ax.destination,'APRS')
        self.assertEqual(ax.path,'WIDE1-1')
        self.assertEqual(ax.raw_info,b'}OK1SRC-7>APRS,TCPIP,OK5TVR-10*:!4944.40N/01322.20E>Test')
        self.assertIsNone(igate_tnc2(ax,'OK5TVR-10')[0])  # no RF->IS echo

    def test_message_requires_directly_heard_recipient(self):
        self.gate.start()
        good = message()
        ok,reason = self.gate.process(good,self.send,True,True)
        self.assertEqual((ok,reason),(False,'recipient_not_heard_direct'))
        self.note_direct('OK1LOCAL-9')
        ok,reason = self.gate.process(good,self.send,True,True)
        self.assertTrue(ok)
        self.assertEqual(len(self.frames),1)
        self.assertIn(b':OK1LOCAL-9:',KissDecoder().feed(self.frames[0])[0])
        self.clock.advance(20)
        ok,reason = self.gate.process(good,self.send,True,True)
        self.assertFalse(ok)
        self.assertEqual(reason,'duplicate')
        self.clock.advance(125)
        ok,reason=self.gate.process(good,self.send,True,True)
        self.assertTrue(ok)

    def test_block_internet_reachable_and_recent_rf_sources(self):
        self.gate.start()
        self.note_direct('OK1LOCAL-9')
        self.gate.process(incoming('OK1LOCAL-9'),self.send,True,True)
        # The recipient is also directly visible on APRS-IS: do not re-gate.
        result=self.gate.process(incoming('OK1LOCAL-9',path='TCPIP*,qAC,T2TEST'),self.send,True,True)
        self.assertEqual(result[1],'sender_not_selected')
        self.assertEqual(self.gate.process(message(),self.send,True,True)[1],
                         'recipient_available_via_internet')
        self.note_direct('OK1SRC-7')
        self.assertEqual(self.gate.process(incoming(),self.send,True,True)[1],
                         'sender_already_on_rf')

    def test_types_objects_and_blocked_paths(self):
        self.gate.start()
        self.assertEqual(self.gate.process(incoming('OK1OTHER-7'),self.send,True,True)[1],
                         'sender_not_selected')
        self.assertEqual(self.gate.process(
            incoming('OK1OTHER-7',';EVENT1   *140800z4944.40N/01322.20E>Test'),self.send,True,True)[0],
            True)
        self.clock.advance(20)
        self.assertEqual(self.gate.process(
            incoming('OK1OTHER-7',';UNLISTED *140800z4944.40N/01322.20E>Test'),self.send,True,True)[1],
            'object_not_selected')
        for via in ('NOGATE,qAC,T2TEST','RFONLY,qAC,T2TEST','TCPXX,qAC,T2TEST',
                    'OK5TVR-10,qAC,T2TEST'):
            with self.subTest(via=via):
                self.assertFalse(self.gate.process(incoming(path=via),self.send,True,True)[0])
        self.assertEqual(self.gate.process(
            incoming(info='}OTHER>APRS,TCPIP,OK1ABC*:>third-party'),self.send,True,True)[1],
            'invalid_packet')

    def test_rate_limits_and_airtime_gap(self):
        self.gate.start()
        self.assertTrue(self.gate.process(incoming(info='!first'),self.send,True,True)[0])
        self.assertEqual(self.gate.process(incoming(info='!second'),self.send,True,True)[1],
                         'min_gap')
        self.clock.advance(20)
        self.assertTrue(self.gate.process(incoming(info='!second'),self.send,True,True)[0])
        self.clock.advance(20)
        self.assertEqual(self.gate.process(incoming(info='!third'),self.send,True,True)[1],
                         'minute_limit')
        self.assertEqual(self.gate.snapshot()['sent_this_hour'],2)
        self.gate.stop()
        self.assertEqual(self.gate.process(incoming(info='!fourth'),self.send,True,True)[1],
                         'preview_only')

    def test_malformed_no_admin_filter_injection_and_fake_input(self):
        invalid=[
            'OK1SRC-7>APRS:>bad\n#filter b/*',
            'INVALID>APRS:!GPS',
            incoming(info='>x'*250),
            incoming(info='?APRS?'),
            incoming(info='}N0ABC>APRS:>test'),
        ]
        for line in invalid:
            with self.subTest(line=line[:40]),self.assertRaises(ValueError):
                parse_tnc2(line)
        self.assertEqual(self.gate.inspect('!!')["reason"],'invalid_packet')


class APRSISReceiveTests(unittest.TestCase):
    def test_fake_verified_aprsis_subscription_and_received_packets(self):
        listener=socket.socket()
        listener.bind(('127.0.0.1',0))
        listener.listen(1)
        port=listener.getsockname()[1]
        ready=threading.Event()
        received=[]
        def fake_server():
            conn,_=listener.accept()
            with conn:
                conn.sendall(b'# test banner\r\n')
                login=conn.recv(1024)
                received.append(login.decode('ascii'))
                conn.sendall(b'# logresp OK5TVR-10 verified, server TEST\r\n')
                conn.sendall(incoming().encode('ascii')[:23])
                time.sleep(.07)
                conn.sendall(incoming().encode('ascii')[23:]+b'\r\n')
                ready.wait(1)
            listener.close()
        th=threading.Thread(target=fake_server,daemon=True);th.start()
        events=queue.Queue(maxsize=500)
        client=APRSISClient('OK5TVR-10','12345','127.0.0.1',port,events,
                           subscription=server_filter(config()))
        client.start()
        try:
            seen=[]
            limit=time.monotonic()+3
            while time.monotonic()<limit and not any(x[1]=='igate_received' for x in seen):
                try:seen.append(events.get(timeout=.2))
                except queue.Empty:pass
            self.assertIn('filter b/OK1SRC-7 o/EVENT1',received[0])
            packets=[x[2] for x in seen if x[1]=='igate_received']
            self.assertEqual(packets,[incoming()])
        finally:
            ready.set()
            client.stop.set()
            client.join(timeout=3)


if __name__=='__main__':
    unittest.main()
