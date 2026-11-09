"""APRS telemetry / overlay regression and integration tests (offline, no real RF)."""
from __future__ import annotations
import json
import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import urlopen

from aprs_telemetry import (RadioWindow, symbol_code, great_circle_km,
                            telemetry_data_payload, metadata_payloads, aprsis_telemetry_lines)
from aprs_station import aprsis_position
from service_config import ServiceConfig
from aprs_service import APRSService
from aprs_features import encode_ui_packet, encode_kiss_data
from aprs_protocol import KissDecoder
from aprs_protocol import decode_ax25
from test_headless import FakeSerial, free_port, wait
from aprs_serial import SerialReader


class TelemetryFormatTests(unittest.TestCase):
    def test_standard_symbol_overlays(self):
        self.assertEqual(symbol_code('\\', '&', 'R'), 'R&')
        self.assertEqual(symbol_code('\\', '#', '1'), '1#')
        self.assertEqual(symbol_code('/', '#', ''), '/#')
        self.assertEqual(aprsis_position('OK5TVR-10', 49.7, 13.3, 'RX', 'I&').split(':!')[1][8], 'I')
        for args in (('/', '#', 'R'), ('\\', '#', 'aa'), ('\\', '#', 'a'),
                     ('x', '#', ''), ('\\', '', ''), ('\\', 'x', '*'), ('\\', '#', '\n')):
            with self.subTest(args=args), self.assertRaises(ValueError):
                symbol_code(*args)

    def test_telemetry_payload_and_metadata(self):
        data={'rx_packets':15,'tx_packets':4,'avg_distance_km':36.6,
              'unique_stations':7,'igate_forwarded':11,'digi_tx':2}
        flags=dict(usb=True,aprsis=True,digi=False,heard=True,tx_error=False,
                   gps=True,telemetry=True,reserved=False)
        pkt=telemetry_data_payload(5,data,'igate',flags)
        self.assertEqual(pkt, 'T#005,015,004,037,007,011,11010110')
        self.assertEqual(telemetry_data_payload(998,{**data,'rx_packets':10000},'digi',flags).split(',')[1],'255')
        for role in ('igate', 'digi'):
            lines=aprsis_telemetry_lines('OK5TVR-10',5,data,role,flags,metadata=True)
            self.assertEqual(len(lines),5)
            self.assertEqual(sum(line.count('T#')>0 for line in lines),1)
            self.assertTrue(all('TCPIP*:' in line and '\r' not in line for line in lines))
            self.assertTrue(all(len(p) <= 67 for p in metadata_payloads(role)))
            self.assertTrue(lines[0].endswith(metadata_payloads(role)[0]))
            self.assertIn(',002,11010110',lines[-1]) if role == 'digi' else None
            self.assertTrue(lines[0].split('TCPIP*:')[1].startswith(':OK5TVR-10:PARM.'))
        with self.assertRaises(ValueError):telemetry_data_payload(1000,data,'igate',flags)
        with self.assertRaises(ValueError):aprsis_telemetry_lines('INJECT\r',0,data,'igate',flags)

    def test_rolling_statistics_15_minutes_and_unique_positions(self):
        now=[100.0]
        stats=RadioWindow(clock=lambda:now[0])
        own=(49.75,13.35)
        stats.record_rx('OK1AAA-7',49.75,13.35,own)
        stats.record_rx('OK1AAA-7',49.75,13.35,own)
        stats.record_rx('OK1BBB-9',49.85,13.35,own)
        stats.record_rx('OK1OBJ',49.85,13.35,own,'TESTOBJ')
        stats.record_tx('digi');stats.record_tx('message');stats.record_gate();stats.record_tx_error()
        view=stats.snapshot()
        self.assertEqual(view['rx_packets'],4)
        self.assertEqual(view['unique_stations'],3)
        self.assertEqual(view['positioned_stations'],2)
        self.assertEqual(view['digi_tx'],1)
        self.assertEqual(view['tx_packets'],2)
        self.assertEqual(view['igate_forwarded'],1)
        self.assertEqual(view['tx_errors'],1)
        self.assertAlmostEqual(view['rx_per_min'],4/15,delta=0.01)
        self.assertEqual(view['forwarded_fraction_pct'],25.0)
        self.assertAlmostEqual(view['avg_distance_km'],5.6,delta=.2)
        self.assertAlmostEqual(view['dx_max_km'],11.1,delta=.2)
        self.assertEqual(view['dx_callsign'],'OK1BBB-9')
        now[0]+=900
        self.assertEqual(stats.snapshot()['rx_packets'],0)
        self.assertIsNone(stats.snapshot()['avg_distance_km'])

    def test_haversine_rejects_bad_positions(self):
        self.assertAlmostEqual(great_circle_km(0,0,0,0),0)
        self.assertAlmostEqual(great_circle_km(0,0,0,1),111.195,delta=.2)
        for loc in [(float('nan'),0,0,0), (91,0,0,0)]:
            with self.assertRaises(ValueError):great_circle_km(*loc)


class ServiceTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.conf=ServiceConfig(Path(self.temp.name)/'config.json').load_or_create()
        self.service=APRSService(self.conf)

    def tearDown(self):
        self.service.messages.close()
        self.service.journal.close()
        self.temp.cleanup()

    def test_defaults_off_and_invalid_symbol(self):
        self.assertFalse(self.conf.data['igate']['telemetry_enabled'])
        self.assertFalse(self.conf.data['digi']['telemetry_enabled'])
        self.assertFalse(self.conf.data['digi']['beacon_enabled'])
        self.assertEqual(self.conf.data['igate']['overlay'],'R')
        self.assertEqual(self.conf.data['digi']['overlay'],'1')
        for changes in ({'igate': {'overlay': 'Q','symbol_table':'/'}},
                        {'digi': {'overlay': '*'}},
                        {'telemetry': {'interval_minutes':1}},
                        {'digi': {'beacon_enabled':True}},
                        {'digi': {'call':'OK1ZZZ-3','telemetry_enabled':True}}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.conf.update(changes)

    def test_station_beacons_and_symbol_config(self):
        self.conf.update({'position':{'latitude':49.7,'longitude':13.3,'beacon_enabled':True},
                          'igate':{'overlay':'I'},'digi':{'beacon_enabled':True,'overlay':'2'}})
        self.service._update_position()
        self.assertIn('I',self.service._beacon_line().split(':!')[1][8])
        self.assertIn('N201318.00E#',aprsis_position('OK5TVR-3',49.7,13.3,'Digi','2#'))

    def test_no_telemetry_without_is_and_digi_inactive(self):
        self.conf.update({'igate':{'telemetry_enabled':True},'digi':{'telemetry_enabled':True}})
        self.assertEqual(self.service._telemetry_send(force_metadata=True),0)
        class FakeClient:
            def __init__(self):
                self.connected=threading.Event();self.connected.set()
                self.lines=[]
                self.connection_epoch=1
            def enqueue_local(self,line,kind):
                self.lines.append((line,kind));return True
        client=FakeClient()
        self.service.igate_client=client
        self.service.telemetry.record_rx('OK1AAA-7',49.8,13.4,(49.7,13.3))
        result=self.service._telemetry_send(force_metadata=True)
        self.assertEqual(result,5)
        self.assertTrue(all(kind=='telemetry' for _,kind in client.lines))
        self.assertTrue(all(line.startswith('OK5TVR-10>') for line,_ in client.lines))
        self.service.digi.start();self.service.radio_ready=True
        client.lines.clear()
        result=self.service._telemetry_send(force_metadata=True)
        self.assertEqual(result,10)
        self.assertEqual(sum(line.startswith('OK5TVR-3>') for line,_ in client.lines),5)
        self.service.config.data['digi']['beacon_enabled']=True
        self.service.config.data['position'].update(latitude=49.7,longitude=13.3)
        self.service.digi_last_position=float('-inf')
        self.service._telemetry_tick()
        self.assertTrue(any(kind=='digi_beacon' for _,kind in client.lines))
        self.service.digi.stop();client.lines.clear();self.service._telemetry_tick()
        self.assertFalse(any(kind=='digi_beacon' for _,kind in client.lines))
        self.service.igate_client=None

    def test_rf_telemetry_encoding_and_pacing_without_aprsis(self):
        """DIGI may schedule RF telemetry ONLY when explicitly enabled/running."""
        self.conf.update({'digi':{'telemetry_enabled':True,
                                  'telemetry_transport':'rf',
                                  'telemetry_rf_path':'DIRECT'}})
        sent=[]
        class FakeRadio:
            def send(self, frame, category=''):
                sent.append((frame,category))
                return True
        self.service.reader=FakeRadio()
        self.assertEqual(self.service._telemetry_send(force_metadata=True), 0)
        self.service.radio_ready=True
        self.service.digi.start()
        self.service.telemetry.record_rx('OK1ZZZ-7',49.8,13.4,(49.7,13.3))
        self.assertEqual(self.service._telemetry_send(force_metadata=True), 5)
        self.assertEqual(len(self.service.rf_telemetry_pending),5)
        # Overlapping (potentially repeated) schedule must be rejected.
        self.assertEqual(self.service._telemetry_send(force_metadata=True),0)
        for expected in range(5):
            self.service.rf_telemetry_next_tx=0
            self.service._rf_telemetry_tick()
            self.assertEqual(len(sent),expected+1)
        self.assertTrue(all(category=='telemetry_rf' for _,category in sent))
        infos=[]
        for raw,category in sent:
            frames=KissDecoder().feed(raw)
            self.assertEqual(len(frames),1)
            packet=decode_ax25(frames[0][1:])
            self.assertEqual(packet.source,'OK5TVR-3')
            self.assertEqual(packet.path,'')
            infos.append(packet.raw_info.decode('ascii'))
        self.assertTrue(infos[0].startswith(':OK5TVR-3 :PARM.'))
        self.assertTrue(infos[-1].startswith('T#000,'))
        self.assertFalse(self.service.rf_telemetry_pending)

    def test_rf_telemetry_requires_save_confirmation(self):
        with self.assertRaisesRegex(ValueError, 'explicit confirmation'):
            self.service._execute('save', {'config':{'digi':{
                'telemetry_enabled':True,'telemetry_transport':'rf'}}})
        self.assertFalse(self.conf.data['digi']['telemetry_enabled'])
        result=self.service._execute('save', {'config':{'digi':{
            'telemetry_enabled':True,'telemetry_transport':'rf'}},
            'confirm_rf_telemetry':True})
        self.assertIn('Nastavení uloženo',result)
        self.assertFalse(self.service.digi.enabled)
        self.assertFalse(self.conf.data['digi']['autostart'])

    def test_rf_telemetry_queue_clears_on_digi_off(self):
        self.conf.update({'digi':{'telemetry_enabled':True,'telemetry_transport':'rf'}})
        class DummyReader:
            def __init__(self):
                self.digi_allowed=threading.Event()
                self.sent=[]
            def send(self,data,category=''):
                self.sent.append((data,category));return True
        reader=DummyReader()
        self.service.reader=reader
        self.service.radio_ready=True
        self.service._enable_digi()
        self.assertEqual(self.service._telemetry_send(force_metadata=True),5)
        self.service._disable_digi()
        self.assertEqual(len(self.service.rf_telemetry_pending),0)
        self.service._rf_telemetry_tick()
        self.assertFalse(reader.sent)
        self.assertFalse(reader.digi_allowed.is_set())

    def test_config_backup_includes_nonsecret_new_fields(self):
        from aprs_operations import backup_document,validate_restore_document
        self.conf.update({'igate':{'symbol_table':'/','symbol':'#','overlay':'','telemetry_enabled':True},
                          'telemetry':{'interval_minutes':30}})
        doc=backup_document(self.conf)
        restored=validate_restore_document(doc)
        self.assertTrue(restored['igate']['telemetry_enabled'])
        self.assertEqual(restored['igate']['symbol_table'],'/')
        self.assertEqual(restored['telemetry']['interval_minutes'],30)
        self.assertFalse(restored['igate']['autostart'])


class RFSerialGuardTests(unittest.TestCase):
    def test_closed_digi_cancels_queued_rf_telemetry(self):
        FakeSerial.incoming=queue.Queue()
        FakeSerial.outgoing=queue.Queue()
        events=queue.Queue()
        stopper=threading.Event()
        reader=SerialReader('FAKEUSB',115200,events,stopper,7)
        with patch('aprs_serial.serial',SimpleNamespace(Serial=FakeSerial)):
            reader.start()
            self.assertTrue(wait(lambda:any(x[1]=='connected' for x in list(events.queue)),2))
            raw=encode_ui_packet('OK5TVR-3','APRS','', 'T#000,001,002,003,004,005,00000000')
            self.assertTrue(reader.send(encode_kiss_data(raw),category='telemetry_rf'))
            self.assertTrue(wait(lambda:any(x[1]=='tx_cancelled' for x in list(events.queue)),2))
            self.assertTrue(FakeSerial.outgoing.empty())
            reader.digi_allowed.set()
            self.assertTrue(reader.send(encode_kiss_data(raw),category='telemetry_rf'))
            self.assertTrue(wait(lambda:not FakeSerial.outgoing.empty(),2))
            stopper.set();reader.join(timeout=3)
            self.assertFalse(reader.is_alive())


class WebTelemetryTests(unittest.TestCase):
    def test_new_controls_on_admin_and_readonly_metrics(self):
        from pathlib import Path
        d=Path(__file__).parent
        control=(d/'web_control.html').read_text(encoding='utf-8')
        operations=(d/'web_operations.html').read_text(encoding='utf-8')
        dashboard=(d/'web_dashboard.html').read_text(encoding='utf-8')
        installer=(d/'install_raspberry.sh').read_text(encoding='utf-8')
        for v in ('igate_overlay','digi_overlay','igate_table','digi_table',
                  'igate_telemetry','digi_telemetry','digi_beacon','telemetry_interval'):
            self.assertIn('id="'+v+'"',control)
        self.assertIn('telemetry_send_now',operations)
        self.assertIn('avg15',dashboard)
        self.assertIn('aprs_telemetry.py',installer)

if __name__=='__main__':unittest.main()
