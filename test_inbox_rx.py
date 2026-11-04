"""Regression checks for RF messages addressed to a base call or local SSID.

No real radio, APRS-IS, or RF transmissions are used.
"""
import tempfile
import unittest
from pathlib import Path
from aprs_features import encode_ui_packet, encode_kiss_data
from aprs_protocol import KissDecoder, decode_ax25
from aprs_messages import MessageManager, message_info
from service_config import ServiceConfig


def rf_packet(sender, target, text, identifier='015'):
    wire = encode_kiss_data(encode_ui_packet(sender, 'APRS', 'WIDE1-1',
                                             message_info(target, text, identifier)))
    decoder = KissDecoder()
    pieces = []
    for i in range(0, len(wire), 3):
        pieces.extend(decoder.feed(wire[i:i+3]))
    assert len(pieces) == 1
    return decode_ax25(pieces[0][1:])


class InboxReceptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.manager = MessageManager(Path(self.tmp.name) / 'msgs.sqlite3', 'OK5TVR-10')

    def tearDown(self):
        self.manager.close()
        self.tmp.cleanup()

    def test_base_call_without_ssid_is_received(self):
        self.assertEqual(self.manager.receive(rf_packet('OK1ABC-9', 'OK5TVR', 'HELLO'), True)['to'], 'OK5TVR')
        self.assertEqual(self.manager.snapshot()['inbox'][0]['recipient'], 'OK5TVR')
        self.assertFalse(self.manager.ack_queue)

    def test_additional_local_ssid_requires_explicit_alias(self):
        p = rf_packet('OK1ABC-9', 'OK5TVR-7', 'HELLO TRACKER')
        self.assertIsNone(self.manager.receive(p, True))
        self.assertEqual(self.manager.snapshot()['heard_messages'][0]['result'], 'other')
        self.manager.configure('OK5TVR-10', 'WIDE1-1', receive_aliases=['OK5TVR-7'])
        self.assertEqual(self.manager.receive(p, True)['to'], 'OK5TVR-7')

    def test_auto_ack_uses_addressed_callsign(self):
        self.manager.configure('OK5TVR-10', 'WIDE1-1', auto_ack=True,
                               receive_aliases=['OK5TVR-7'])
        self.manager.receive(rf_packet('OK1ABC-9', 'OK5TVR-7', 'ACK PLEASE'), True)

        class Reader:
            sent = []
            def send(self, packet, category):
                self.sent.append(packet)
                return True

        reader = Reader()
        self.assertEqual(self.manager.tx_tick(reader, True), 'ACK')
        reply = decode_ax25(KissDecoder().feed(reader.sent[0])[0][1:])
        self.assertEqual(reply.source, 'OK5TVR-7')
        self.assertEqual(reply.raw_info, b':OK1ABC-9 :ack015')


class AliasConfigTests(unittest.TestCase):
    def test_aliases_are_persisted_and_cannot_use_another_operator(self):
        with tempfile.TemporaryDirectory() as root:
            cfg = ServiceConfig(Path(root) / 'config.json').load_or_create()
            cfg.update({'messages': {'receive_aliases': ['OK5TVR-7']}})
            self.assertEqual(ServiceConfig(cfg.path).load_or_create().data['messages']['receive_aliases'], ['OK5TVR-7'])
            with self.assertRaises(ValueError):
                cfg.update({'messages': {'receive_aliases': ['OK1ABC-7']}})


if __name__ == '__main__':
    unittest.main()
