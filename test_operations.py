"""Unit and simulated KISS/API checks for objects, diagnostics and safe backups.
No hardware or public APRS-IS connection is required.
"""
from __future__ import annotations
import json
import queue
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen, Request

from aprs_journal import OperationsJournal
from aprs_operations import validate_object, object_info, status_info, position_info, make_rf_frame
from aprs_protocol import KissDecoder, decode_ax25
from aprs_features import encode_kiss_data, encode_ui_packet
from service_config import ServiceConfig, validate_config
from test_headless import FakeSerial, wait, free_port
from aprs_service import APRSService


def example(**changes):
    e = {'name':'LORA-VRX','kind':'object','latitude':49.7384,'longitude':13.3736,
         'symbol_table':'/', 'symbol':'>', 'comment':'Test object',
         'repeat':False,'interval_minutes':30}
    e.update(changes)
    return e


class ProtocolTests(unittest.TestCase):
    def test_object_living_killed_utc_and_item(self):
        at=datetime(2026, 11, 4, 9, 8, tzinfo=timezone.utc)
        p=object_info(example(),now=at)
        self.assertTrue(p.startswith(';LORA-VRX *040908z4944.30N/01322.42E>'))
        self.assertIn('Test object',p)
        self.assertEqual(object_info(example(),False,now=at)[10],'_')
        item=object_info(example(kind='item'),now=at)
        self.assertTrue(item.startswith(')LORA-VRX!4944.30N/01322.42E>'))
        frame=make_rf_frame('OK5TVR-10','WIDE1-1',p)
        packet=decode_ax25(frame)
        self.assertEqual(packet.source,'OK5TVR-10')
        self.assertEqual(packet.destination,'APZKIS')
        self.assertEqual(packet.path,'WIDE1-1')
        self.assertEqual(packet.raw_info.decode('ascii'),p)
    def test_bad_names_paths_and_coordinates(self):
        for bad in [example(name='TOO_LONG_ABC'),example(name='A\nB'),
                    example(latitude=999),example(comment='ě'),
                    example(symbol=''),example(interval_minutes=2)]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                validate_object(bad)
        with self.assertRaises(ValueError):make_rf_frame('OK5TVR-10','TCPIP','>TEST')
        with self.assertRaises(ValueError):status_info('á')
        with self.assertRaises(ValueError):position_info(100,13)
        with self.assertRaises(ValueError):validate_config({'objects':{'entries':[example(),example()]}})
    def test_backup_is_secret_free_and_restore_rf_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=ServiceConfig(Path(tmp)/'a'/'config.json').load_or_create()
            a.update({'igate':{'autostart':True},'digi':{'autostart':True},
                      'messages':{'auto_ack':True},'objects':{'entries':[example(repeat=True)]}},passcode='12345')
            backup=a.export_backup()
            source=json.dumps(backup)
            self.assertNotIn('12345',source)
            self.assertNotIn(a.secrets['admin_token'],source)
            b=ServiceConfig(Path(tmp)/'b'/'config.json').load_or_create()
            old=b.secrets['admin_token'];b.restore_backup(backup)
            self.assertEqual(b.secrets['admin_token'],old)
            self.assertFalse(b.data['igate']['autostart'])
            self.assertFalse(b.data['digi']['autostart'])
            self.assertFalse(b.data['messages']['auto_ack'])
            self.assertEqual(b.data['objects']['entries'][0]['name'],'LORA-VRX')
            with self.assertRaises(ValueError):b.restore_backup({'format':'incorrect','config':{}})
            self.assertEqual(b.data['objects']['entries'][0]['name'],'LORA-VRX')
    def test_journal_privacy_and_csv_spreadsheet_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.sqlite3'
            j=OperationsJournal(path)
            j.add('RX','KISS','OK5ABC-7','APRS','WIDE1-1','=HYPERLINK("bad")','RX')
            self.assertEqual(j.count(),1)
            self.assertIn("'=HYPERLINK",j.csv_export().decode('utf-8-sig'))
            j.close()
            j=OperationsJournal(path)
            self.assertEqual(j.recent(1)[0]['source'],'OK5ABC-7')
            j.clear();self.assertEqual(j.count(),0)
            j.close()


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.conf=ServiceConfig(Path(self.tmp.name)/'config.json').load_or_create()
        self.port=free_port()
        self.conf.update({'serial':{'port':'FAKEUSB'},'web':{'port':self.port}})
        FakeSerial.incoming=queue.Queue();FakeSerial.outgoing=queue.Queue()
        self.patch=patch('aprs_serial.serial',SimpleNamespace(Serial=FakeSerial))
        self.patch.start()
        self.s=APRSService(self.conf)
        self.thread=threading.Thread(target=self.s.run,daemon=True)
        self.thread.start()
        self.assertTrue(wait(lambda:self.s.radio_ready))
    def tearDown(self):
        self.s.stop.set();self.thread.join(5)
        self.patch.stop();self.tmp.cleanup()
        self.assertFalse(self.thread.is_alive())
    @property
    def base(self):return 'http://127.0.0.1:'+str(self.port)
    def get(self,path,admin=True):
        if admin:path+=('?admin='+self.conf.secrets['admin_token'])
        return urlopen(self.base+path,timeout=4)
    def api(self,action,code=200,**kwargs):
        headers={'Content-Type':'application/json','X-APRS-Admin':self.conf.secrets['admin_token']}
        req=Request(self.base+'/api/control',method='POST',headers=headers,
                    data=json.dumps({'action':action,**kwargs}).encode())
        try:
            with urlopen(req,timeout=5) as response:
                self.assertEqual(response.status,code);return json.load(response)
        except HTTPError as e:
            self.assertEqual(e.code,code);return json.load(e)
    def test_new_web_restricted_and_english(self):
        for path in ['/operations','/diagnostics','/api/objects','/api/diagnostics','/api/backup','/api/journal.csv']:
            with self.assertRaises(HTTPError) as exc:self.get(path,admin=False)
            self.assertEqual(exc.exception.code,403)
            with self.get(path) as r:
                self.assertEqual(r.status,200)
        with self.get('/assets/web_locale.js',admin=False) as r:
            self.assertIn(b'Objects & RF',r.read())
        with self.get('/api/backup') as r:
            config=json.load(r)
        self.assertIn('objects',config['config'])
        self.assertNotIn('admin_token',str(config))
    def test_rf_object_status_and_logging(self):
        self.assertFalse(self.s.object_schedule_enabled)
        self.assertTrue(FakeSerial.outgoing.empty())
        self.assertTrue(self.api('object_save',entry=example())['ok'])
        with self.get('/api/objects') as r:
            obj=json.load(r)
            self.assertEqual(obj['objects'][0]['name'],'LORA-VRX')
        self.assertEqual(self.api('object_send',code=400,name='LORA-VRX',kind='object')['ok'],False)
        self.assertTrue(self.api('object_send',name='LORA-VRX',kind='object',confirm=True)['ok'])
        self.assertTrue(wait(lambda:not FakeSerial.outgoing.empty()))
        encoded=FakeSerial.outgoing.get()
        packets=KissDecoder().feed(encoded)
        self.assertEqual(len(packets),1)
        packet=decode_ax25(packets[0][1:])
        self.assertTrue(packet.raw_info.startswith(b';LORA-VRX *'))
        self.assertTrue(wait(lambda:self.s.journal.count()>4))
        with self.get('/api/diagnostics') as r:
            report=json.load(r)
            self.assertTrue(report['diagnostics']['usb_connected'])
            self.assertTrue(any(entry['direction']=='TX' for entry in report['entries']))
        with self.get('/api/journal.csv') as r:
            self.assertIn(b'KISS',r.read())
        self.assertFalse(self.s.object_schedule_enabled)
        self.assertEqual(self.api('objects_on',code=400,confirm=True)['ok'],False)
        self.assertTrue(self.api('object_save',entry=example(repeat=True))['ok'])
        self.assertTrue(self.api('objects_on',confirm=True)['ok'])
        self.assertTrue(self.s.object_schedule_enabled)
        self.assertTrue(self.api('objects_off')['ok'])
    def test_health_alert_and_config_import(self):
        self.s.usb_connected_at=time.monotonic()-1900
        self.s.last_valid_rx_at=None
        self.s._health_tick()
        with self.get('/api/diagnostics') as r:
            report=json.load(r)
            self.assertEqual(report['diagnostics']['health'],'quiet')
        self.assertEqual(self.api('health_save',health={'quiet_warning_minutes':40})['ok'],True)
        with self.get('/api/backup') as r:
            backup=json.load(r)
        backup['config']['igate']['autostart']=True
        backup['config']['digi']['autostart']=True
        backup['config']['messages']['auto_ack']=True
        self.assertTrue(self.api('backup_restore',confirm=True,backup=backup)['ok'])
        self.assertFalse(self.conf.data['igate']['autostart'])
        self.assertFalse(self.conf.data['digi']['autostart'])
        self.assertFalse(self.conf.data['messages']['auto_ack'])
        self.assertFalse(self.s.object_schedule_enabled)

if __name__=='__main__':unittest.main()
