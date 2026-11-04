"""Regression/safety tests for GPS beacon and APRS digipeating. No RF transmitted."""
from __future__ import annotations
import json
import queue
import socket
import threading
import time
import unittest
import urllib.request

from aprs_features import APRSISClient, MonitorState, address_bytes, encode_ui_packet, igate_tnc2
from aprs_digi import DigiConfig, DigiRepeater, read_ui_frame, rewrite_digi
from aprs_station import aprs_coord, aprsis_position, decimal_coordinate, maidenhead_center
from aprs_kiss_monitor import decode_ax25
from web_panel import WebPanel


class DigiSafetyTests(unittest.TestCase):
    def mk(self,path='WIDE1-1',source='TEST-7',payload='>PING'):
        return encode_ui_packet(source,'APRS',path,payload)

    def rewrite(self,path,mode='fill',trace=False,source='TEST-7',payload='>PING',call='OK5TVR-3'):
        raw=self.mk(path,source=source,payload=payload)
        return rewrite_digi(raw,DigiConfig(call,mode,trace))

    def test_wide1_fillin_and_fcs_free(self):
        rewritten,reason=self.rewrite('WIDE1-1,WIDE2-1')
        self.assertEqual(reason,'OK')
        self.assertEqual(decode_ax25(rewritten).path,'OK5TVR-3*,WIDE2-1')
        self.assertEqual(decode_ax25(rewritten).source,'TEST-7')
        self.assertEqual(read_ui_frame(rewritten).info,b'>PING')
        self.assertEqual(rewritten[-5:],b'>PING')

    def test_fillin_rejects_wide2(self):
        for path in ('WIDE2-1','WIDE2-2','WIDE3-3','TRACE2-1'):
            with self.subTest(path=path):self.assertIsNone(self.rewrite(path)[0])

    def test_regional_wide2_decrement_trace(self):
        r,why=self.rewrite('WIDE2-2',mode='regional')
        self.assertEqual(why,'OK')
        self.assertEqual(decode_ax25(r).path,'OK5TVR-3*,WIDE2-1')
        r2,reason=rewrite_digi(r,DigiConfig('OK5XYZ-3','regional'))
        self.assertEqual(reason,'OK')
        self.assertEqual(decode_ax25(r2).path,'OK5TVR-3,OK5XYZ-3*')
        # Preserve entire payload with no encoding changes.
        self.assertEqual(read_ui_frame(r2).info,read_ui_frame(self.mk('WIDE2-2')).info)

    def test_regional_wide2_one(self):
        r,why=self.rewrite('WIDE2-1',mode='regional')
        self.assertEqual(decode_ax25(r).path,'OK5TVR-3*')

    def test_trace_is_opt_in(self):
        self.assertIsNone(self.rewrite('TRACE2-2','regional',False)[0])
        r,why=self.rewrite('TRACE2-2','regional',True)
        self.assertEqual(why,'OK')
        self.assertEqual(decode_ax25(r).path,'OK5TVR-3*,TRACE2-1')

    def test_explicit_call(self):
        r,why=self.rewrite('OK5TVR-3')
        self.assertEqual(why,'OK')
        self.assertEqual(decode_ax25(r).path,'OK5TVR-3*')
        self.assertIsNone(self.rewrite('OK5TVR-3',source='OK5TVR-3')[0])

    def test_first_unused_only(self):
        self.assertIsNone(self.rewrite('OTHER,OK5TVR-3')[0])
        self.assertIsNone(self.rewrite('WIDE3-3,WIDE1-1',mode='regional')[0])

    def test_no_internet_loop_or_queries(self):
        for path in ('TCPIP','TCPXX','WIDE1-1,TCPIP','WIDE1-1,QAR'):
            with self.subTest(path=path):self.assertIsNone(self.rewrite(path,mode='regional')[0])
        base=self.mk('WIDE1-1')[:-5]
        for message in ('?APRS?','}TEST-7>APRS,TCPIP*:>INFO'):
            with self.subTest(message=message):
                self.assertIsNone(rewrite_digi(base+message.encode('ascii'),DigiConfig('OK5TVR-3'))[0])

    def test_nogate_rfonlystays_on_rf(self):
        for path in ('WIDE1-1,NOGATE','WIDE1-1,RFONLY'):
            r,why=self.rewrite(path)
            self.assertEqual(why,'OK')
            self.assertEqual(decode_ax25(r).path,'OK5TVR-3*,'+path.split(',')[1])
            self.assertIsNone(igate_tnc2(decode_ax25(r),'OK5TVR-10')[0])

    def test_full_hops_and_valid_ax25(self):
        path=['DIGI01','DIGI02','DIGI03','DIGI04','DIGI05','DIGI06','DIGI07','WIDE2-2']
        addresses=['APRS','TEST-7']+path
        raw=b''.join(address_bytes(a,last=(ix==len(addresses)-1),repeated=(2<=ix<9))
                     for ix,a in enumerate(addresses))+b'\x03\xf0>hi'
        r,reason=rewrite_digi(raw,DigiConfig('OK5TVR-3','regional'))
        self.assertIsNone(r)
        self.assertIn('8 DIGI',reason)
        # Reject 9 DIGI addresses in receive too.
        bad=raw[:14]+address_bytes('MORE',last=False)+raw[14:]
        with self.assertRaises(ValueError):read_ui_frame(bad)

    def test_unrelated_ax25_rejected(self):
        p=self.mk('WIDE1-1')
        index=7*3
        self.assertIsNone(rewrite_digi(p[:index]+b'\x13\xf0'+p[index+2:],DigiConfig('OK5TVR-3'))[0])

    def test_duplicate_and_viscous_suppression(self):
        cfg=DigiConfig('OK5TVR-3','fill',delay_s=4)
        engine=DigiRepeater(cfg);engine.start()
        raw=self.mk('WIDE1-1,WIDE2-1')
        self.assertIn('Plánováno',engine.receive(raw,100.0))
        self.assertIsNone(engine.ready(102))
        self.assertIn('čeká',engine.receive(raw,102))
        # Another digipeater relays same info before our 4 s delay.
        relay,_=rewrite_digi(raw,DigiConfig('OK5QTH-3'))
        self.assertIn('zrušen',engine.receive(relay,103))
        self.assertIsNone(engine.ready(110))
        self.assertEqual(engine.stats['suppressed'],1)

    def test_duplicate_after_tx_30s(self):
        engine=DigiRepeater(DigiConfig('OK5TVR-3','fill',delay_s=0));engine.start()
        raw=self.mk()
        engine.receive(raw,100)
        p=engine.ready(100)
        self.assertIsNotNone(p)
        engine.mark_queued(p.signature,100)
        self.assertIn('již retransmitován',engine.receive(raw,105))
        self.assertIn('Plánováno',engine.receive(raw,131))

    def test_rate_limit_and_stop(self):
        engine=DigiRepeater(DigiConfig('OK5TVR-3','fill',delay_s=0,max_per_min=1,min_gap_s=1))
        engine.start()
        engine.receive(self.mk(payload='>FIRST'),100)
        p=engine.ready(100);self.assertIsNotNone(p);engine.mark_queued(p.signature,100)
        engine.receive(self.mk(payload='>SECOND'),102)
        self.assertIsNone(engine.ready(102));self.assertEqual(engine.stats['rate_limited'],1)
        engine.stop()
        engine.receive(self.mk(payload='>THIRD'),110)
        self.assertIsNone(engine.ready(110))
        self.assertFalse(engine.enabled)

    def test_reject_corrupt_h_bits(self):
        raw=self.mk('WIDE1-1,WIDE2-1')
        data=bytearray(raw)
        data[14+7+6]|=0x80  # second DIGI appears used after an unused hop
        self.assertIsNone(rewrite_digi(bytes(data),DigiConfig('OK5TVR-3','regional'))[0])

    def test_no_rf_when_disabled(self):
        engine=DigiRepeater(DigiConfig('OK5TVR-3'))
        self.assertEqual(engine.receive(self.mk(),10),'Vypnuto')
        self.assertIsNone(engine.ready(20))


class StationPositionTests(unittest.TestCase):
    def test_coordinate_formats(self):
        self.assertEqual(aprs_coord(49.7384,True),'4944.30N')
        self.assertEqual(aprs_coord(13.3736,False),'01322.42E')
        self.assertEqual(aprs_coord(-33.5,True),'3330.00S')
        self.assertEqual(aprs_coord(-180,False),'18000.00W')
        self.assertEqual(decimal_coordinate('49,5',True),49.5)
        for val in ('nan','inf','-91','missing'):
            with self.subTest(val=val),self.assertRaises(ValueError):decimal_coordinate(val,True)

    def test_is_beacon_pos_and_no_rf(self):
        text=aprsis_position('OK5TVR-10',49.7384,13.3736,'RX IGate UVK1')
        self.assertEqual(text,'OK5TVR-10>APZKIS,TCPIP*:!4944.30NR01322.42E&RX IGate UVK1')
        self.assertNotIn('qAR',text)
        for comment in ('český komentář','bad\nSECOND>APRS:','X'*44):
            with self.subTest(comment=comment),self.assertRaises(ValueError):
                aprsis_position('OK5TVR-10',49,13,comment)

    def test_locator_is_only_approximate(self):
        la,lo=maidenhead_center('JN69PS')
        self.assertAlmostEqual(la,49.7708333,places=5)
        self.assertAlmostEqual(lo,13.2916667,places=5)
        with self.assertRaises(ValueError):maidenhead_center('WRONG')

    def test_web_includes_local_position_not_rf_station(self):
        state=MonitorState();state.set_own_position(dict(call='OK5TVR-10',lat=49.73,lon=13.3,beacon=False))
        state.update_digi({'enabled':False,'tx_written':0})
        v=state.snapshot()
        self.assertEqual(v['station_count'],0)
        self.assertEqual(v['own_position']['call'],'OK5TVR-10')
        self.assertFalse(v['digi']['enabled'])
        web=WebPanel(state)
        try:
            port=web.start(port=0)
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/state') as r:
                obj=json.load(r)
            self.assertEqual(obj['own_position']['lat'],49.73)
            self.assertEqual(obj['station_count'],0)
        finally:web.close()

    def test_fake_aprsis_login_and_position_beacon(self):
        srv=socket.socket();srv.bind(('127.0.0.1',0));srv.listen(1)
        port=srv.getsockname()[1]
        done=threading.Event();got=[]
        def handler():
            try:
                conn,_=srv.accept()
                with conn:
                    conn.settimeout(4);conn.sendall(b'# TEST SERVER\r\n')
                    buffer=b''
                    while b'\n' not in buffer:buffer+=conn.recv(1024)
                    got.append(buffer.decode())
                    conn.sendall(b'# logresp OK5TVR-10 verified, server TEST\r\n')
                    buffer=b''
                    while b'\n' not in buffer:buffer+=conn.recv(1024)
                    got.append(buffer.decode())
            except Exception as exc: got.append(str(exc))
            finally:done.set();srv.close()
        threading.Thread(target=handler,daemon=True).start()
        events=queue.Queue()
        client=APRSISClient('OK5TVR-10','12345','127.0.0.1',port,events)
        beacon=aprsis_position('OK5TVR-10',49.7384,13.3736)
        client.configure_position(beacon,30)
        client.start()
        self.assertTrue(done.wait(5),'Position was not sent after verified login')
        client.stop.set()
        self.assertIn('vers OK5TVR-KISS 1.4',got[0])
        self.assertEqual(got[1].strip(),beacon)


if __name__ == '__main__':unittest.main()
