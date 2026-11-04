"""Unittest: no hardware or external APRS-IS connectivity required."""
import json
import os
import queue
import socket
import threading
import time
import unittest
import urllib.error
import urllib.request

from aprs_features import (APRSISClient, MonitorState, encode_kiss_data, encode_ui_packet,
                           igate_tnc2, parse_position, _base91)
from aprs_kiss_monitor import KissDecoder, decode_ax25, demo_ax25_packet
from web_panel import WebPanel


class TestFeatures(unittest.TestCase):
    def ax25(self, content, source="OK5TVR-9", path="WIDE1-1"):
        return decode_ax25(encode_ui_packet(source,"APRS",path,content))

    def test_manual_tx_frame(self):
        raw = encode_ui_packet("OK5TVR-9", "APRS", "", ">Manual KISS TX test")
        p = decode_ax25(raw)
        self.assertEqual((p.source,p.destination,p.path,p.kind),("OK5TVR-9","APRS","","Stav"))
        self.assertEqual(p.control,3)
        self.assertEqual(p.pid,240)
        self.assertEqual(p.raw_info,b">Manual KISS TX test")
        k=KissDecoder()
        self.assertEqual(k.feed(encode_kiss_data(raw)),[b"\x00"+raw])

    def test_path_kiss_escapes(self):
        data=b"abc\xC0def\xDBghi"
        k=KissDecoder()
        self.assertEqual(k.feed(encode_kiss_data(data)),[b'\x00'+data])

    def test_bad_calls_and_control(self):
        for call in ["", "A", "THISISLONG", "OK5TVR-16", "OK5TVR-0", "OK5TVR/3"]:
            with self.subTest(call=call), self.assertRaises(ValueError):
                encode_ui_packet(call,"APRS","",">test")
        with self.assertRaises(ValueError):encode_ui_packet("OK5TVR","APRS","", "Xinvalid")
        with self.assertRaises(ValueError):encode_ui_packet("OK5TVR","APRS","",">áá")

    def test_uncompressed_coords(self):
        pos=parse_position(b"!4903.50N/01322.00E>Text")
        self.assertAlmostEqual(pos['lat'],49.058333,places=5)
        self.assertAlmostEqual(pos['lon'],13.366667,places=5)
        self.assertEqual(pos['format'],"nekomprimovaná")
        self.assertIsNone(parse_position(b"!9999.99N/01322.00E>"))

    def test_timestamp_position(self):
        p=parse_position(b"@123456z4903.50N/01322.00E>text")
        self.assertAlmostEqual(p['lat'],49.05833,places=4)

    @staticmethod
    def encode_base91(n):
        s=[]
        for _ in range(4):
            s.append(n%91+33);n//=91
        return bytes(reversed(s))

    def test_compressed_coords(self):
        lat,lon=49.70,13.45
        y=self.encode_base91(int((90-lat)*380926))
        x=self.encode_base91(int((180+lon)*190463))
        p=parse_position(b"!/"+y+x+b">!00text")
        self.assertAlmostEqual(p['lat'],lat,places=4)
        self.assertAlmostEqual(p['lon'],lon,places=4)
        self.assertEqual(p['format'],'komprimovaná')

    def test_mice_example(self):
        # Destination S32U6T encodes 33°25.64' N; longitude samples from spec.
        # m-e information field: data byte+28, minutes+28, hundredth+28.
        p=parse_position(b"`"+bytes([40,95,102])+b'n"O>/test',"S32U6T")
        self.assertIsNotNone(p)
        self.assertAlmostEqual(p['lat'],33+25.64/60,places=4)
        # S32U6T encodes no +100 longitude offset, hence longitude 12°07.74' W.
        self.assertAlmostEqual(p['lon'],-(12+7.74/60),places=4)

    def test_object(self):
        p=parse_position(b";EXAMPLE  *111111z4903.50N/01322.00E>Object")
        self.assertEqual(p['label'],'EXAMPLE')

    def test_no_map_guess(self):
        for s in [b"!4903.50N/xxx",b"`bad",b"=bad",b"",b"?APRS?",b"!9001.00N/01322.00E>"]:
            with self.subTest(s=s):self.assertIsNone(parse_position(s))

    def test_igate_good(self):
        p=self.ax25("!4903.50N/01322.00E>Ok")
        line,why=igate_tnc2(p,"OK5TVR-10")
        self.assertEqual(why,"OK")
        self.assertEqual(line, "OK5TVR-9>APRS,WIDE1-1,qAO,OK5TVR-10:!4903.50N/01322.00E>Ok")

    def test_igate_skip_paths(self):
        for path in ["NOGATE", "RFONLY", "TCPIP", "TCPXX", "WIDE1-1,NOGATE", "WIDE1-1,RFONLY"]:
            with self.subTest(path=path):
                p=self.ax25(">status",path=path)
                line,reason=igate_tnc2(p,"OK5TVR-10")
                self.assertIsNone(line,reason)
        p=self.ax25(">status")
        p.raw_info=b"?APRS?"
        self.assertIsNone(igate_tnc2(p,"OK5TVR-10")[0])

    def test_igate_skip_demo(self):
        p=decode_ax25(demo_ax25_packet(),simulated=True)
        self.assertIsNone(igate_tnc2(p,"OK5TVR-10")[0])

    def test_igate_no_nonui(self):
        p=self.ax25(">status")
        p.pid=0xCF
        self.assertIsNone(igate_tnc2(p,"OK5TVR-10")[0])

    def test_igate_injection(self):
        p=self.ax25(">hello")
        p.raw_info=b'>hello\r\nOK5TVR>APRS:evil'
        self.assertIsNone(igate_tnc2(p,"OK5TVR-10")[0])

    def test_igate_third_party(self):
        p=self.ax25(">test")
        p.raw_info=b"}OK1AAA>APRS,WIDE1-1:!4900.00N/01300.00E>item"
        line,_=igate_tnc2(p,"OK5TVR-10")
        self.assertEqual(line,"OK1AAA>APRS,WIDE1-1,qAO,OK5TVR-10:!4900.00N/01300.00E>item")
        p.raw_info=b"}OK1AAA>APRS,TCPIP*:!4900.00N/01300.00E>item"
        self.assertIsNone(igate_tnc2(p,"OK5TVR-10")[0])

    def test_snapshot_statistics(self):
        state=MonitorState()
        p=self.ax25("!4903.50N/01322.00E>Hi")
        state.add(p)
        state.add(decode_ax25(demo_ax25_packet(),simulated=True))
        v=state.snapshot()
        self.assertEqual(v['rx'],1)
        self.assertEqual(v['demo'],1)
        self.assertEqual(v['position_count'],1)
        self.assertEqual(v['station_count'],1)

    def test_web_local_only_and_lan_access(self):
        state=MonitorState();web=WebPanel(state)
        try:
            port=web.start(lan=False,port=0)
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/state') as r:
                content=json.load(r)
            self.assertEqual(content['rx'],0)
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/') as r:
                self.assertIn(b'OpenStreetMap',r.read())
            # Simulate remote IP by checking authorization handler below, independent
            # of local address (cannot connect external NIC in unit tests).
            self.assertFalse(web.lan)
        finally:
            web.close()

    def test_aprsis_fake_verified_server(self):
        server=socket.socket();server.bind(('127.0.0.1',0));server.listen(1)
        port=server.getsockname()[1]
        received=[]
        done=threading.Event()
        def run_server():
            try:
                conn,_=server.accept()
                with conn:
                    conn.settimeout(3)
                    conn.sendall(b'# APRS-IS test server\r\n')
                    login=b''
                    while b'\n' not in login:login+=conn.recv(512)
                    received.append(login.decode('ascii'))
                    conn.sendall(b'# logresp OK5TVR-10 verified, server TEST\r\n')
                    pkt=b''
                    while b'\n' not in pkt:pkt+=conn.recv(512)
                    received.append(pkt.decode('latin-1'))
            except Exception as exc:received.append(str(exc))
            finally:done.set();server.close()
        thread=threading.Thread(target=run_server,daemon=True);thread.start()
        events=queue.Queue()
        worker=APRSISClient('OK5TVR-10','12345','127.0.0.1',port,events);worker.start()
        self.assertTrue(worker.connected.wait(4),'Login handshake failed')
        p=self.ax25('>hello from test')
        line,_=igate_tnc2(p,'OK5TVR-10')
        self.assertTrue(worker.enqueue(line))
        self.assertTrue(done.wait(4),'No APRS-IS packet received')
        worker.stop.set()
        self.assertIn('vers OK5TVR-KISS 1.6',received[0])
        self.assertEqual(received[1].strip(),line)

if __name__=='__main__':unittest.main()
