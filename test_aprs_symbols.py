"""APRS symbol decoding and map state regressions, no radio hardware needed."""
import unittest
from aprs_features import parse_position, MonitorState
from aprs_protocol import decode_ax25
from aprs_features import encode_ui_packet


class SymbolMapTests(unittest.TestCase):
    def test_uncompressed_primary_and_overlay(self):
        primary=parse_position(b'!4944.40N/01322.20E>Car')
        self.assertEqual(primary['symbol'], '/>')
        secondary=parse_position(b'!4944.40NR01322.20E&IGate')
        self.assertEqual(secondary['symbol'], 'R&')

    def test_compressed_symbol(self):
        # Four valid base91 digits for lat and lon, primary table, > glyph.
        position=parse_position(b'!/' + b'!' * 8 + b'>test')
        self.assertIsNotNone(position)
        self.assertEqual(position['symbol'], '/>')

    def test_object_and_third_party_symbols(self):
        object_info=b';SHELTER  *111111z4944.40N/01322.20E>Object'
        obj=parse_position(object_info)
        self.assertEqual(obj['symbol'], '/>')
        nested=parse_position(b'}OK1XYZ-7>APRS:!4944.40NR01322.20E&IGate')
        self.assertEqual(nested['source'],'OK1XYZ-7')
        self.assertEqual(nested['symbol'],'R&')

    def test_station_state_exposes_symbol(self):
        raw=encode_ui_packet('OK1ABC-7','APRS','WIDE1-1','!4944.40N/01322.20E>CAR')
        p=decode_ax25(raw)
        self.assertEqual(p.symbol,'/>')
        state=MonitorState()
        state.add(p)
        entry={item['call']:item for item in state.snapshot()['stations']}['OK1ABC-7']
        self.assertEqual(entry['symbol'],'/>')
        # Non-position status must not erase the last valid icon.
        status=decode_ax25(encode_ui_packet('OK1ABC-7','APRS','','>QRV'))
        state.add(status)
        entry={item['call']:item for item in state.snapshot()['stations']}['OK1ABC-7']
        self.assertEqual(entry['symbol'],'/>')


if __name__ == '__main__':
    unittest.main()
