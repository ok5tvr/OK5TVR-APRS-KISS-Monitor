"""v2.1 TNC network, archive, weather and configuration regression tests."""
from __future__ import annotations
import queue
import socket
import tempfile
import threading
import time
from pathlib import Path
import unittest
from aprs_features import encode_ui_packet, encode_kiss_data
from aprs_protocol import KissDecoder, decode_ax25
from aprs_tcp import TCPKissReader, TCPKissHub
from aprs_archive import APRSArchive
from aprs_weather import decode_weather
from service_config import validate_config


def packet(payload="!4944.40N/01322.20E>GPS"):
    return decode_ax25(encode_ui_packet("OK1ABC-7","APRS","",payload))


class TNCV21Tests(unittest.TestCase):
    def test_config_defaults_safe_and_invalid_network_settings(self):
        cfg=validate_config({})
        self.assertEqual(cfg['tnc']['transport'],'serial')
        self.assertFalse(cfg['tnc']['kiss_server_enabled'])
        self.assertFalse(cfg['tnc']['kiss_server_tx'])
        self.assertEqual(cfg['archive']['retention_days'],30)
        with self.assertRaises(ValueError):
            validate_config({'tnc':{'transport':'other'}})
        with self.assertRaises(ValueError):
            validate_config({'tnc':{'kiss_server_tx':True}})
        with self.assertRaises(ValueError):
            validate_config({'tnc':{'kiss_server_enabled':True,
                                     'kiss_server_host':'0.0.0.0','kiss_server_tx':True}})
        with self.assertRaises(ValueError):
            validate_config({'archive':{'max_rows':9}})
        with self.assertRaises(ValueError):
            validate_config({'tnc':{'transport':'tcp','tcp_port':8001,'kiss_server_enabled':True,
                                     'kiss_server_port':8001}})

    def test_archive_and_weather_persist_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'archive.sqlite3'
            p=packet()
            w=decode_weather(b'_11092215c120s010g015t050r010p020P030h65b10132')
            self.assertIsNotNone(w)
            a=APRSArchive(path,30,1000)
            a.add(p,w)
            self.assertEqual(a.summary()['packets'],1)
            self.assertEqual(len(a.positions("OK1ABC-7")),1)
            self.assertEqual(len(a.weather_rows()),1)
            a.add(decode_ax25(encode_ui_packet("OK1ABC-7","APRS","",">status")))
            a.close()
            reopened=APRSArchive(path,30,1000)
            try:
                self.assertEqual(reopened.summary()['packets'],2)
                self.assertEqual(len(reopened.positions("OK1ABC-7")),1)
                self.assertEqual(reopened.weather_rows()[0]['temperature_c'],10.0)
                self.assertEqual(reopened.weather_rows()[0]['humidity_pct'],65.0)
                self.assertEqual(reopened.weather_rows()[0]['wind_kmh'],16.09)
                with self.assertRaises(ValueError):
                    reopened.positions("'%")
                with self.assertRaises(ValueError):
                    reopened.packets(10000)
            finally:
                reopened.close()

    def test_weather_rejects_invalid_and_not_wx(self):
        self.assertIsNone(decode_weather(b'>not weather t120b10001'))
        self.assertIsNone(decode_weather(b'_11092215t...b.....'))
        self.assertEqual(decode_weather(b'_11092215c090s005g010t032h00b10132')['humidity_pct'],100)
        self.assertIsNone(decode_weather(b'_11092215c999s999'))

    def test_tcp_hub_is_rx_only_and_streams_kiss(self):
        hub=TCPKissHub('127.0.0.1',0)
        hub.start()
        try:
            with socket.create_connection(('127.0.0.1',hub.port),timeout=2) as conn:
                conn.settimeout(2)
                time.sleep(0.05)
                p=packet()
                hub.publish(p.raw_ax25)
                data=conn.recv(1024)
                packets=KissDecoder().feed(data)
                self.assertEqual(len(packets),1)
                self.assertEqual(packets[0][0],0)
                self.assertEqual(decode_ax25(packets[0][1:]).source,'OK1ABC-7')
                conn.sendall(encode_kiss_data(p.raw_ax25))
                time.sleep(0.1)
                self.assertEqual(hub.snapshot()['tx_accepted'],0)
                self.assertGreaterEqual(hub.snapshot()['tx_rejected'],1)
        finally:
            hub.close()

    def test_tcp_client_reads_frames_from_network_tnc(self):
        listener=socket.socket()
        listener.bind(('127.0.0.1',0))
        listener.listen(1)
        port=listener.getsockname()[1]
        p=packet()
        done=threading.Event()
        def server():
            try:
                conn,_=listener.accept()
                with conn:
                    conn.sendall(encode_kiss_data(p.raw_ax25))
                    done.wait(1)
            finally:
                listener.close()
        th=threading.Thread(target=server,daemon=True);th.start()
        events=queue.Queue()
        stopper=threading.Event()
        client=TCPKissReader('127.0.0.1',port,events,stopper,1)
        client.start()
        try:
            observed=[]
            end=time.monotonic()+2.0
            while time.monotonic()<end and not any(e[1]=='frame' for e in observed):
                try: observed.append(events.get(timeout=.2))
                except queue.Empty:pass
            frames=[e[2] for e in observed if e[1]=='frame']
            self.assertEqual(len(frames),1)
            self.assertEqual(frames[0].source,'OK1ABC-7')
        finally:
            stopper.set();done.set();client.join(timeout=2)

    def test_tcp_hub_rejects_lan_transmit_configuration(self):
        with self.assertRaises(ValueError):
            TCPKissHub('0.0.0.0',8001,allow_tx=True)


if __name__=='__main__':
    unittest.main()
