"""Integration test: selective IS->RF is operator controlled through APRSService.

No actual radio or APRS-IS network service is accessed.
"""
import queue
import tempfile
import threading
import unittest
from pathlib import Path

from aprs_features import encode_ui_packet
from aprs_protocol import decode_ax25, KissDecoder
from aprs_service import APRSService
from service_config import ServiceConfig


RULES = {'calls':['OK1SRC-7'], 'objects':['EVENT1'],
         'types':['message','position','object'], 'rf_path':'',
         'heard_minutes':30, 'max_per_minute':2, 'max_per_hour':8,
         'min_gap_seconds':15, 'duplicate_seconds':120}


class FakeTNC:
    port='FAKE'
    def __init__(self):
        self.isrf_allowed = threading.Event()
        self.digi_allowed = threading.Event()
        self.sent = []

    def send(self, frame, category='manual'):
        if category == 'igate_is_to_rf' and not self.isrf_allowed.is_set():
            return False
        self.sent.append((frame, category))
        return True


class FakeAPRSIS:
    call='OK5TVR-10'
    def __init__(self):
        self.connected = threading.Event()
        self.connected.set()
        self.stop = threading.Event()
    def join(self, timeout=None):
        pass


class ISRFServiceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conf = ServiceConfig(Path(self.tmp.name)/'config.json').load_or_create()
        self.service = APRSService(self.conf)
        self.reader = FakeTNC()
        self.service.reader = self.reader
        self.service.radio_ready = True
        self.service._execute('isrf_save', {'rules':RULES})
        self.service.igate_client = FakeAPRSIS()
        self.service.igate_events = queue.Queue(maxsize=500)

    def tearDown(self):
        self.service.archive.close()
        self.service.messages.close()
        self.service.journal.close()
        self.tmp.cleanup()

    def send_from_internet(self, info='!4944.40N/01322.20E>TEST', source='OK1SRC-7'):
        line=f'{source}>APRS,TCPIP*,qAC,T2TEST:{info}'
        self.service.igate_events.put((-1,'igate_received',line))
        self.service._handle_events()

    def test_no_isrf_traffic_before_admin_confirmation_and_off_cancels_next(self):
        self.send_from_internet()
        self.assertFalse(self.reader.sent)
        self.assertEqual(self.service.isrf.snapshot()['counters']['preview_only'],1)
        with self.assertRaises(ValueError):
            self.service._execute('isrf_on', {})
        self.assertFalse(self.reader.isrf_allowed.is_set())
        self.service._execute('isrf_on', {'confirm':True})
        self.assertTrue(self.reader.isrf_allowed.is_set())
        self.send_from_internet()
        self.assertEqual(len(self.reader.sent),1)
        frame,category=self.reader.sent[0]
        self.assertEqual(category,'igate_is_to_rf')
        parsed=decode_ax25(KissDecoder().feed(frame)[0][1:])
        self.assertEqual(parsed.source,'OK5TVR-10')
        self.assertIn(b'TCPIP,OK5TVR-10*:',parsed.raw_info)
        self.service._execute('isrf_off', {})
        self.assertFalse(self.reader.isrf_allowed.is_set())
        self.send_from_internet(info='!4944.41N/01322.21E>TEST')
        self.assertEqual(len(self.reader.sent),1)

    def test_controlled_message_to_directly_heard_station_only(self):
        self.service._execute('isrf_on', {'confirm':True})
        info=':OK1LOC-9 :Hello{01'
        self.send_from_internet(info=info)
        self.assertEqual(len(self.reader.sent),0)
        self.assertEqual(self.service.isrf.snapshot()['counters']['recipient_not_heard_direct'],1)
        rf=decode_ax25(encode_ui_packet('OK1LOC-9','APRS','','>Here'))
        self.service.isrf.note_rf(rf)
        self.send_from_internet(info=info)
        self.assertEqual(len(self.reader.sent),1)
        self.assertIn(b':OK1LOC-9 :Hello{01',KissDecoder().feed(self.reader.sent[0][0])[0])

    def test_disconnected_tnc_or_aprsis_cancels_runtime_permission(self):
        self.service._execute('isrf_on', {'confirm':True})
        self.service.igate_events.put((-1,'igate_status','Odpojeno: server closed'))
        self.service._handle_events()
        self.assertFalse(self.service.isrf.active)
        self.assertFalse(self.reader.isrf_allowed.is_set())
        self.service._execute('isrf_on', {'confirm':True})
        self.service._disable_igate()
        self.assertFalse(self.reader.isrf_allowed.is_set())

    def test_filter_config_is_saved_without_enabling_rf_tx(self):
        c = self.conf.public_view()['is_to_rf']
        self.assertEqual(c['calls'],['OK1SRC-7'])
        self.assertFalse(self.service.isrf.active)
        self.assertEqual(self.service._execute('isrf_check',{
            'line':'OK1SRC-7>APRS,TCPIP*,qAC,T2TEST:!4944.40N/01322.20E>GPS'
        })['reason'],'matched')
        self.assertFalse(self.reader.sent)


if __name__=='__main__':
    unittest.main()
