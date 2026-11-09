"""Position and H-bit regressions for v1.8.1; RF hardware is not required."""
import math
import unittest

from aprs_features import MonitorState, parse_position, encode_ui_packet
from aprs_geo import distance_bearing
from aprs_protocol import decode_ax25, demo_ax25_packet, KissDecoder


class PositionRoutesTests(unittest.TestCase):
    @staticmethod
    def packet(info:bytes, source='OK1ABC-7', dest='APRS', path=(), repeated=()):
        def addr(call, last=False, used=False):
            c,_,suffix=call.partition('-')
            ssid=int(suffix) if suffix else 0
            return bytes(ord(ch)<<1 for ch in c.upper().ljust(6)) + bytes([0x60|(ssid<<1)|int(last)|(0x80 if used else 0)])
        addresses=[dest,source,*path]
        raw=b''.join(addr(c,i==len(addresses)-1,used=(i-2) in repeated if i>=2 else False)
                     for i,c in enumerate(addresses)) + b'\x03\xf0'+info
        return decode_ax25(raw)

    def test_mice_raw_position_and_classification(self):
        p=self.packet(b"`"+bytes([40,95,102])+b'n"O>/test','OK1KZE-1','S32U6T',('WIDE1-1',))
        self.assertEqual(p.kind,'Mic-E')
        self.assertEqual(p.position_format,'Mic-E')
        self.assertAlmostEqual(p.latitude,33+25.64/60,places=5)
        self.assertAlmostEqual(p.longitude,-(12+7.74/60),places=5)
        self.assertTrue(p.heard_direct)
        self.assertIn('GPS ',p.summary)

    def test_direct_via_from_ax25_hbits(self):
        info=b'!4944.40N/01322.20E>RF example'
        direct=self.packet(info,path=('WIDE1-1','WIDE2-1'))
        repeated=self.packet(info,path=('WIDE1-1','OK0BBK-2'),repeated=(0,))
        repeated2=self.packet(info,path=('WIDE1-1','OK0BBK-2'),repeated=(0,1))
        self.assertTrue(direct.heard_direct)
        self.assertFalse(repeated.heard_direct)
        self.assertFalse(repeated2.heard_direct)
        self.assertEqual(repeated.path,'WIDE1-1*,OK0BBK-2')
        self.assertEqual(repeated2.path,'WIDE1-1,OK0BBK-2*')
        self.assertEqual(direct.path,'WIDE1-1,WIDE2-1')

    def test_nmea_rmc_gga_gll(self):
        rmc=(b'$GPRMC,123519,A,4944.1234,N,01322.5678,E,022.4,084.4,230394,003.1,W')
        nmea_gga=b'$GNGGA,124001,4944.1234,N,01322.5678,E,1,08,0.9,545.4,M,46.9,M,,'
        nmea_gll=b'$GPGLL,4944.1234,N,01322.5678,E,124001,A'
        for payload in [rmc,nmea_gga,nmea_gll]:
            with self.subTest(payload=payload):
                point=parse_position(payload)
                self.assertIsNotNone(point)
                self.assertAlmostEqual(point['lat'],49+44.1234/60,places=5)
                self.assertAlmostEqual(point['lon'],13+22.5678/60,places=5)
        self.assertIsNone(parse_position(rmc.replace(b',A,',b',V,')))
        self.assertIsNone(parse_position(nmea_gga.replace(b',1,08,',b',0,08,')))
        self.assertIsNone(parse_position(nmea_gll[:-1]+b'V'))
        self.assertIsNone(parse_position(b'$GPRMC,123519,A,9959.1234,N,01322.5678,E,,,,,,'))

    def test_nmea_checksum_validation(self):
        sentence=b'GPRMC,123519,A,4944.1234,N,01322.5678,E,022.4,084.4,230394,003.1,W'
        checksum=0
        for c in sentence:checksum ^= c
        valid=b'$'+sentence+b'*'+f'{checksum:02X}'.encode('ascii')
        self.assertIsNotNone(parse_position(valid))
        self.assertIsNone(parse_position(valid[:-2]+b'FF' if checksum!=0xff else valid[:-2]+b'00'))

    def test_object_item_compressed_and_timestamp(self):
        examples=[b';TESTOBJ  *111111z4944.40N/01322.20E>',
                  b')ITEM!4944.40N/01322.20E>',
                  b'@123456z4944.40N/01322.20E>comment',
                  b'!4944.40N/01322.20E>text']
        for payload in examples:
            self.assertIsNotNone(parse_position(payload))
        self.assertEqual(parse_position(examples[0])['kind'],'objekt')
        self.assertEqual(parse_position(examples[1])['kind'],'položka')

    def test_third_party_position_not_direct(self):
        inner=b'}OK1XYZ-7>APRS,WIDE1-1:!4944.40N/01322.20E>packet'
        p=self.packet(inner,source='OK1GAT',path=())
        self.assertFalse(p.heard_direct)
        self.assertEqual(p.position_source,'OK1XYZ-7')
        self.assertEqual(p.position_format,'3rd-party nekomprimovaná')
        state=MonitorState()
        state.set_own_position({'lat':49.73,'lon':13.36,'call':'OK5TVR-10'})
        state.add(p)
        st={item['call']:item for item in state.snapshot()['stations']}
        self.assertIn('OK1XYZ-7',st)
        self.assertFalse(st['OK1XYZ-7']['direct'])
        self.assertIsNotNone(st['OK1XYZ-7']['distance_km'])
        self.assertIsNone(st['OK1XYZ-7']['position_direct'])
        self.assertIsNone(parse_position(b'}INVALID:!4944.40N/01322.20E>'))

    def test_geo_distance_initial_bearing(self):
        origin=(49.74,13.37)
        north=distance_bearing(*origin,50.74,13.37)
        self.assertAlmostEqual(north['distance_km'],111.2,delta=0.5)
        self.assertAlmostEqual(north['bearing_deg'],0,delta=0.01)
        self.assertEqual(north['compass_cs'],'S')
        east=distance_bearing(*origin,49.74,14.37)
        self.assertTrue(80<east['bearing_deg']<100)
        self.assertIn(east['compass_cs'],('V','VSV','VJV'))
        colocated=distance_bearing(*origin,*origin)
        self.assertIsNone(colocated['bearing_deg'])
        with self.assertRaises(ValueError):distance_bearing(float('nan'),0,0,0)

    def test_position_and_route_coloring_snapshot(self):
        state=MonitorState()
        p=self.packet(b'!4944.40N/01322.20E>DIRECT',path=('WIDE1-1',))
        state.set_own_position({'lat':49.73,'lon':13.36,'call':'OK5TVR-10'})
        state.add(p)
        sample=state.snapshot()
        s=sample['stations'][0]
        self.assertTrue(s['direct']);self.assertTrue(s['position_direct'])
        self.assertEqual(s['direct_count'],1)
        self.assertEqual(s['via_count'],0)
        self.assertEqual(sample['direct_count'],1)
        self.assertEqual(sample['history'][0]['direct'],True)
        self.assertIsNotNone(s['bearing_deg'])
        p=self.packet(b'!4944.50N/01322.30E>VIA',path=('WIDE1-1',),repeated=(0,))
        state.add(p)
        s=state.snapshot()['stations'][0]
        self.assertFalse(s['direct']);self.assertFalse(s['position_direct'])
        self.assertEqual(s['direct_count'],1)
        self.assertEqual(s['via_count'],1)
        self.assertEqual(state.snapshot()['direct_count'],0)
        state.set_own_position(None)
        self.assertIsNone(state.snapshot()['stations'][0]['distance_km'])

    def test_direct_with_no_position_still_highlight(self):
        packet=self.packet(b'>QRV',source='OK1ABC-7')
        state=MonitorState();state.add(packet)
        s=state.snapshot()['stations'][0]
        self.assertTrue(s['direct'])
        self.assertIsNone(s['distance_km'])
        self.assertIsNone(s['lat'])

    def test_object_not_labelled_as_rf_station(self):
        p=self.packet(b';SHELTER  *111111z4944.40N/01322.20E>Object',source='OK1ABC-7')
        self.assertTrue(p.heard_direct)
        state=MonitorState();state.add(p)
        rows={item['call']:item for item in state.snapshot()['stations']}
        self.assertTrue(rows['OK1ABC-7']['direct'])
        self.assertIsNone(rows['SHELTER']['direct'])
        self.assertIsNone(rows['SHELTER']['position_direct'])
        self.assertTrue(rows['SHELTER']['is_object'])

if __name__=='__main__':unittest.main()
