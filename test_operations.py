"""v1.6 tests: APRS objects, portability, durable logs and HTTP access."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from aprs_operations import object_payload, validate_object_request, Journal, backup_document, validate_restore_document
from aprs_features import encode_ui_packet, encode_kiss_data
from service_config import ServiceConfig

class OperationsTests(unittest.TestCase):
    def test_object_live_and_kill_format(self):
        now=dt.datetime(2026,11,4,11,22,tzinfo=dt.timezone.utc)
        live=object_payload('TEST OBJ',49.75,13.25,'APRS test',now=now)
        killed=object_payload('TEST OBJ',49.75,13.25,'APRS test',alive=False,now=now)
        self.assertEqual(live[:18],';TEST OBJ *041122z')
        self.assertEqual(killed[:18],';TEST OBJ _041122z')
        self.assertIn('4945.00N/01315.00Er',live)
        self.assertGreater(len(encode_kiss_data(encode_ui_packet('OK5TVR-10','APRS','WIDE1-1',live))),30)
    def test_bad_objects_are_rejected(self):
        for name in ('', 'ABCDEFGHIJ', 'ČESKO', 'bad:obj'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                object_payload(name,49,13)
        with self.assertRaises(ValueError):object_payload('OK5TVR',95,13)
        with self.assertRaises(ValueError):object_payload('OK5TVR',49,13,'é')
        with self.assertRaises(ValueError):validate_object_request({'name':'X','lat':49,'lon':13,'path':'TCPIP'})
    def test_journal_persists(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'op.sqlite3';j=Journal(path)
            j.log('RX','accepted','OK5TVR','APRS','hello');j.log('DIGI','rejected','OK5TVR','APRS','direct')
            self.assertEqual(len(j.read()),2)
            self.assertEqual(j.read(category='RX')[0]['source'],'OK5TVR')
            j.close();self.assertEqual(len(Journal(path).read()),2)
    def test_backup_is_sanitized_and_restores_tx_off(self):
        with tempfile.TemporaryDirectory() as d:
            c=ServiceConfig(Path(d)/'config.json').load_or_create()
            c.update({'digi':{'autostart':True},'igate':{'autostart':True},'messages':{'auto_ack':True}},passcode='12345')
            obj=backup_document(c);text=json.dumps(obj)
            self.assertNotIn('12345',text)
            self.assertNotIn(c.secrets['admin_token'],text)
            clean=validate_restore_document(obj)
            self.assertFalse(clean['digi']['autostart']);self.assertFalse(clean['igate']['autostart']);self.assertFalse(clean['messages']['auto_ack'])
            with self.assertRaises(ValueError):validate_restore_document({'format':'bad','version':1,'config':{}})

if __name__=='__main__':unittest.main()

class OperationalWebTests(unittest.TestCase):
    def test_endpoints_transmit_and_restore(self):
        import queue,threading,time
        from types import SimpleNamespace
        from unittest.mock import patch
        from urllib.request import urlopen,Request
        from urllib.error import HTTPError
        from test_headless import FakeSerial,free_port,wait
        from aprs_service import APRSService
        from aprs_protocol import KissDecoder,decode_ax25
        with tempfile.TemporaryDirectory() as d:
            conf=ServiceConfig(Path(d)/'config.json').load_or_create()
            port=free_port();conf.update({'serial':{'port':'FAKEUSB'},'web':{'port':port},'position':{'latitude':49.73,'longitude':13.37}})
            FakeSerial.incoming=queue.Queue();FakeSerial.outgoing=queue.Queue()
            with patch('aprs_serial.serial',SimpleNamespace(Serial=FakeSerial)):
                svc=APRSService(conf);t=threading.Thread(target=svc.run,daemon=True);t.start()
                try:
                    self.assertTrue(wait(lambda:svc.radio_ready))
                    base=f'http://127.0.0.1:{port}'
                    with self.assertRaises(HTTPError) as e:urlopen(base+'/api/backup')
                    self.assertEqual(e.exception.code,403)
                    with urlopen(base+'/api/backup?admin='+conf.secrets['admin_token']) as r:backup=json.load(r)
                    self.assertNotIn('passcode',json.dumps(backup))
                    with urlopen(base+'/operations?admin='+conf.secrets['admin_token']) as r:self.assertIn(b'APRS objects',r.read())
                    def post(action,**k):
                        req=Request(base+'/api/control',data=json.dumps({'action':action,**k}).encode(),method='POST',headers={'X-APRS-Admin':conf.secrets['admin_token'],'Content-Type':'application/json'})
                        try:
                            with urlopen(req,timeout=5) as r:return r.status,json.load(r)
                        except HTTPError as e:return e.code,json.load(e)
                    self.assertEqual(post('object_send',name='MYOBJ',lat=49,lon=13)[0],400)
                    self.assertEqual(post('object_send',confirm=True,name='MYOBJ',lat=49.73,lon=13.37,path='DIRECT')[0],200)
                    self.assertTrue(wait(lambda:not FakeSerial.outgoing.empty()))
                    ax=KissDecoder().feed(FakeSerial.outgoing.get())[0][1:]
                    self.assertEqual(decode_ax25(ax).source,'OK5TVR-10')
                    self.assertTrue(decode_ax25(ax).raw_info.startswith(b';MYOBJ    *'))
                    self.assertEqual(post('object_send',confirm=True,name='MYOBJ',lat=49.73,lon=13.37)[0],400)
                    self.assertEqual(post('restore_config',confirm=True,backup=backup)[0],200)
                    with urlopen(base+'/api/journal?admin='+conf.secrets['admin_token']) as r:
                        entries=json.load(r)
                    self.assertTrue(any(x['category']=='OBJECT' for x in entries))
                finally:
                    svc.stop.set();t.join(timeout=5)
                self.assertFalse(t.is_alive())
