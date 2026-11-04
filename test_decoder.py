import unittest
from aprs_kiss_monitor import KissDecoder, decode_ax25, demo_ax25_packet, position_summary

class TestMonitor(unittest.TestCase):
    def test_demo_frame(self):
        p = decode_ax25(demo_ax25_packet())
        self.assertEqual(p.destination, 'APRS')
        self.assertEqual(p.source, 'TEST-7')
        self.assertEqual(p.path, 'WIDE1-1')
        self.assertEqual(p.kind, 'Pozice')
        self.assertIn('GPS 49.05833, 13.36667', p.summary)

    def test_fragmentation(self):
        raw = b'\x00' + demo_ax25_packet()
        frame = b'\xC0' + raw + b'\xC0'
        k = KissDecoder()
        self.assertEqual(k.feed(b'garbage' + frame[:12]), [])
        self.assertEqual(k.feed(frame[12:]), [raw])

    def test_multiple_frames_and_escape(self):
        k = KissDecoder()
        data = b'\xC0\x00\x41\xDB\xDC\x42\xDB\xDD\xC0\xC0\x00abc\xC0'
        self.assertEqual(k.feed(data), [b'\x00A\xC0B\xDB', b'\x00abc'])

    def test_corrupt_escape(self):
        k = KissDecoder()
        self.assertEqual(k.feed(b'\xC0\x00abc\xDB\x01\xC0'), [])
        self.assertEqual(k.errors, 1)
        self.assertEqual(k.feed(b'\xC0\x00ok\xC0'), [b'\x00ok'])

    def test_bad_ax25(self):
        p = decode_ax25(b'\x00\x01')
        self.assertEqual(p.kind, 'RAW')

    def test_invalid_position(self):
        self.assertIsNone(position_summary(b'!9999.99N/01322.00E>test'))

    def test_aprs_message(self):
        def addr(call, ssid=0, final=False):
            return bytes(ord(ch) << 1 for ch in call.ljust(6)) + bytes([0x60 | (ssid << 1) | int(final)])
        p = decode_ax25(addr('APRS') + addr('OK5TVR', 0, True) + b'\x03\xF0:OK1ABC   :Ahoj{11')
        self.assertEqual(p.kind, 'Zpráva')
        self.assertIn('Komu OK1ABC', p.summary)

if __name__ == '__main__':
    unittest.main()
