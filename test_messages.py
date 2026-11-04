"""APRS messaging tests. No RF or public APRS-IS access."""
from __future__ import annotations
import json
import queue
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from aprs_features import encode_kiss_data, encode_ui_packet
from aprs_messages import MessageManager, normalize_path, message_info, ack_info, parse_message
from aprs_protocol import KissDecoder, decode_ax25
from aprs_service import APRSService
from service_config import ServiceConfig
from test_headless import FakeSerial, wait, free_port

class DummyReader:
    def __init__(self): self.sent=[]
    def send(self, payload, category): self.sent.append((payload,category));return True


def pack(source, target, message):
    return decode_ax25(encode_ui_packet(source, 'APRS', '', message))


class FormatTests(unittest.TestCase):
    def test_address_and_ids(self):
        info=message_info('ok1abc-9','Hello APRS','032')
        self.assertEqual(info, ':OK1ABC-9 :Hello APRS{032')
        self.assertEqual(parse_message(info.encode()), dict(target='OK1ABC-9',kind='message',id='032',text='Hello APRS',reply_ack=None))
        self.assertEqual(parse_message(b':OK5TVR-10:ack032')['kind'],'ack')
        self.assertEqual(parse_message(b':OK5TVR-10:rej032')['kind'],'rej')
        self.assertEqual(parse_message(b':OK5TVR-10:Test{01}02')['reply_ack'],'02')
        self.assertEqual(ack_info('OK5TVR-10','032'), ':OK5TVR-10:ack032')
        self.assertIsNone(parse_message(b'>Status text'))
        self.assertIsNone(parse_message(b':BLN1     :Bulletin'))
        self.assertIsNone(parse_message(b':OK5TVR-10:'))
    def test_body_and_path_validation(self):
        self.assertEqual(normalize_path('direct'),'')
        self.assertEqual(normalize_path('wide1-1,wide2-1'),'WIDE1-1,WIDE2-1')
        for bad in ('WIDE7-7','TRACE2-2','TCPIP','WIDE1-1,RFONLY','WIDE1-1,WIDE1-1','WIDE1-1,WIDE2-1,WIDE2-2','NOGATE','QAR','WIDE2-7'):
            with self.subTest(path=bad),self.assertRaises(ValueError): normalize_path(bad)
        for body in ('', 'a'*68,'Ahoj světe','Ahoj\nOK','{1','}2'):
            with self.subTest(body=body),self.assertRaises(ValueError): message_info('OK5TVR-10',body,'001')
        with self.assertRaises(ValueError): message_info('BAD-16','Hello','001')

class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=Path(self.tmp.name)/'messages.sqlite3'
        self.manager=MessageManager(self.db,'OK5TVR-10')
        self.rd=DummyReader()
    def tearDown(self):
        self.manager.close();self.tmp.cleanup()
    def test_outbox_ack_matching_and_retry(self):
        item=self.manager.compose('OK1ABC-9','TEST APRS ZPRAVY','WIDE1-1,WIDE2-1')
        self.assertEqual(item['message_id'],'001')
        self.assertEqual(self.manager.tx_tick(self.rd,True),'message')
        data,category=self.rd.sent.pop()
        self.assertEqual(category,f'msg:{item["id"]}')
        encoded=KissDecoder().feed(data)[0]
        packet=decode_ax25(encoded[1:])
        self.assertEqual(packet.source,'OK5TVR-10')
        self.assertEqual(packet.path,'WIDE1-1,WIDE2-1')
        self.assertEqual(packet.raw_info.decode(),':OK1ABC-9 :TEST APRS ZPRAVY{001')
        self.manager.tx_written(category)
        self.assertEqual(self.manager.snapshot()['outbox'][0]['status'],'waiting_ack')
        self.manager.receive(pack('OK3SPF','OK5TVR-10',':OK5TVR-10:ack001'), True)
        self.assertEqual(self.manager.snapshot()['outbox'][0]['status'],'waiting_ack')
        self.manager.receive(pack('OK1ABC-9','OK5TVR-10',':OK5TVR-10:ack999'),True)
        self.assertEqual(self.manager.snapshot()['outbox'][0]['status'],'waiting_ack')
        self.manager.receive(pack('OK1ABC-9','OK5TVR-10',':OK5TVR-10:ack001'),True)
        self.assertEqual(self.manager.snapshot()['outbox'][0]['status'],'ack')
        self.assertIsNone(self.manager.tx_tick(self.rd,True))
    def test_retry_and_failure(self):
        self.manager.configure('OK5TVR-10','',False,30,2)
        item=self.manager.compose('OK1ABC','test','DIRECT')
        self.manager.tx_tick(self.rd,True)
        self.manager.tx_written(f'msg:{item["id"]}')
        with self.manager.lock,self.manager.db:
            self.manager.db.execute('UPDATE outbox SET next_retry=0 WHERE id=?',(item['id'],))
        self.manager._last_tx_at=-1000000
        self.assertEqual(self.manager.tx_tick(self.rd,True),'message')
        self.manager.tx_written(f'msg:{item["id"]}')
        with self.manager.lock,self.manager.db:
            self.manager.db.execute('UPDATE outbox SET next_retry=0 WHERE id=?',(item['id'],))
        self.manager._last_tx_at=-1000000
        self.assertEqual(self.manager.tx_tick(self.rd,True),'failed')
        self.assertEqual(self.manager.snapshot()['outbox'][0]['status'],'failed')
    def test_inbox_duplicate_and_auto_ack(self):
        self.manager.configure('OK5TVR-10','WIDE1-1',True,45,3)
        incoming=pack('OK1ABC-9','OK5TVR-10',':OK5TVR-10:Hello there{71')
        self.assertEqual(self.manager.receive(incoming, True)['kind'],'message')
        self.assertEqual(self.manager.receive(incoming, True)['duplicate'],True)
        snap=self.manager.snapshot()
        self.assertEqual(snap['stats']['inbox'],1)
        self.assertEqual(snap['inbox'][0]['duplicates'],1)
        self.assertEqual(len(self.manager.ack_queue),1)
        self.assertEqual(self.manager.tx_tick(self.rd,True),'ACK')
        data,category=self.rd.sent.pop()
        p=decode_ax25(KissDecoder().feed(data)[0][1:])
        self.assertEqual(p.raw_info,b':OK1ABC-9 :ack71')
        self.manager.tx_written(category)
        self.assertEqual(self.manager.snapshot()['inbox'][0]['ack_sent'],1)
    def test_manual_ack_when_auto_off_and_restart_halts_tx(self):
        incoming=pack('OK1ABC','OK5TVR-10',':OK5TVR-10:Hallo{B1')
        self.manager.receive(incoming,True)
        self.assertEqual(len(self.manager.ack_queue),0)
        id=self.manager.snapshot()['inbox'][0]['id']
        self.manager.acknowledge_manual(id)
        self.assertEqual(self.manager.tx_tick(self.rd,True),'ACK')
        self.manager.tx_written(f'msgack:{id}')
        self.assertEqual(self.manager.snapshot()['inbox'][0]['ack_sent'],1)
        self.manager.compose('OK1ABC','Next message')
        self.manager.close()
        self.manager=MessageManager(self.db,'OK5TVR-10')
        self.assertEqual(self.manager.snapshot()['outbox'][0]['status'],'interrupted')
        self.assertIsNone(self.manager.tx_tick(self.rd,True))
        self.assertEqual(self.manager.snapshot()['inbox'][0]['text'],'Hallo')
    def test_rejection_stops_retries(self):
        item=self.manager.compose('OK1ABC-9','Ready for test')
        self.manager.tx_tick(self.rd,True)
        self.manager.tx_written('msg:'+str(item['id']))
        self.manager.receive(pack('OK1ABC-9','OK5TVR-10',
                                  ':OK5TVR-10:rej'+item['message_id']),True)
        self.assertEqual(self.manager.snapshot()['outbox'][0]['status'],'rej')
    def test_manual_rej_frame(self):
        self.manager.receive(pack('OK1ABC','OK5TVR-10',':OK5TVR-10:Bad message{X3'),True)
        incoming_id=self.manager.snapshot()['inbox'][0]['id']
        self.manager.acknowledge_manual(incoming_id,reject=True)
        self.assertEqual(self.manager.tx_tick(self.rd,True),'ACK')
        p=decode_ax25(KissDecoder().feed(self.rd.sent[0][0])[0][1:])
        self.assertEqual(p.raw_info,b':OK1ABC   :rejX3')
    def test_config_migrates_from_v13(self):
        tmp=tempfile.TemporaryDirectory()
        try:
            conf=ServiceConfig(Path(tmp.name)/'config.json').load_or_create()
            older=json.loads(conf.path.read_text());older.pop('messages')
            conf.path.write_text(json.dumps(older))
            restored=ServiceConfig(conf.path).load_or_create()
            self.assertFalse(restored.data['messages']['auto_ack'])
            self.assertEqual(restored.data['messages']['path'],'WIDE1-1')
        finally:
            tmp.cleanup()
    def test_no_unrequested_tx(self):
        self.manager.receive(pack('OK1ABC','OK5TVR-10',':OK5TVR-10:hello{001'),True)
        self.assertFalse(self.manager.ack_queue)
        self.assertIsNone(self.manager.tx_tick(self.rd,True))
        self.assertFalse(self.rd.sent)

class WebMessageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.conf=ServiceConfig(Path(self.tmp.name)/'config.json').load_or_create()
        self.port=free_port()
        self.conf.update({'serial':{'port':'FAKEUSB'},'web':{'port':self.port}})
        FakeSerial.incoming=queue.Queue(); FakeSerial.outgoing=queue.Queue()
        self.patch_serial=patch('aprs_serial.serial',SimpleNamespace(Serial=FakeSerial));self.patch_serial.start()
        self.service=APRSService(self.conf)
        self.thread=threading.Thread(target=self.service.run,daemon=True);self.thread.start()
        self.assertTrue(wait(lambda:self.service.radio_ready))
    def tearDown(self):
        self.service.stop.set();self.thread.join(5)
        self.patch_serial.stop();self.tmp.cleanup()
        self.assertFalse(self.thread.is_alive())
    def api(self,action,expected=200,admin=True,**data):
        headers={'Content-Type':'application/json'}
        if admin:headers['X-APRS-Admin']=self.conf.secrets['admin_token']
        req=Request(f'http://127.0.0.1:{self.port}/api/control',method='POST',
                    headers=headers,data=json.dumps({'action':action,**data}).encode())
        try:
            with urlopen(req,timeout=6) as r: self.assertEqual(r.status,expected);return json.load(r)
        except HTTPError as e:
            self.assertEqual(e.code,expected);return json.load(e)
    def test_messaging_page_security_and_rf_transmit(self):
        base=f'http://127.0.0.1:{self.port}'
        key=self.conf.secrets['admin_token']
        with self.assertRaises(HTTPError) as e:urlopen(base+'/messages')
        self.assertEqual(e.exception.code,403)
        with urlopen(base+'/messages?admin='+key) as r:
            data=r.read().decode()
        self.assertIn('Inbox',data);self.assertIn('Outbox',data)
        with urlopen(base+'/api/messages?admin='+key) as r: view=json.load(r)
        self.assertEqual(view['stats']['inbox'],0)
        self.assertIn('error',self.api('message_send',expected=403,admin=False,target='OK1ABC',text='Hi'))
        self.assertIn('error',self.api('message_send',expected=400,target='OK1ABC',text='Hi'))
        self.assertIn('error',self.api('save',expected=400,config={'messages':{'auto_ack':True}}))
        self.assertTrue(self.api('message_send',target='OK1ABC-9',text='Hello!',path='DIRECT',confirm=True)['ok'])
        self.assertTrue(wait(lambda:not FakeSerial.outgoing.empty()))
        data=FakeSerial.outgoing.get()
        p=decode_ax25(KissDecoder().feed(data)[0][1:])
        self.assertEqual(p.source,'OK5TVR-10');self.assertEqual(p.path,'')
        self.assertTrue(p.raw_info.startswith(b':OK1ABC-9 :Hello!{' ))
        self.assertTrue(wait(lambda:self.service.messages.snapshot()['outbox'][0]['status']=='waiting_ack'))
        our_id=self.service.messages.snapshot()['outbox'][0]['message_id']
        FakeSerial.incoming.put(encode_kiss_data(encode_ui_packet('OK1ABC-9','APRS','',':OK5TVR-10:ack'+our_id)))
        self.assertTrue(wait(lambda:self.service.messages.snapshot()['outbox'][0]['status']=='ack'))
        FakeSerial.incoming.put(encode_kiss_data(encode_ui_packet('OK1ABC-9','APRS','',':OK5TVR-10:Reply{A1')))
        self.assertTrue(wait(lambda:self.service.messages.snapshot()['stats']['inbox']==1))
        self.assertTrue(FakeSerial.outgoing.empty(),'Automatic ACK must be off on fresh install')
        inboxid=self.service.messages.snapshot()['inbox'][0]['id']
        self.assertEqual(self.api('message_ack',id=inboxid,expected=400)['ok'],False)
        self.assertEqual(self.api('message_ack',id=inboxid,confirm=True)['ok'],True)
        self.service.messages._last_tx_at=-1000000
        self.assertTrue(wait(lambda:not FakeSerial.outgoing.empty()))
        ack=decode_ax25(KissDecoder().feed(FakeSerial.outgoing.get())[0][1:])
        self.assertEqual(ack.raw_info,b':OK1ABC-9 :ackA1')
        with urlopen(base+'/api/messages?admin='+key) as r: reply=json.load(r)
        self.assertEqual(reply['stats']['inbox'],1)
        self.assertEqual(reply['outbox'][0]['status'],'ack')

if __name__=='__main__':unittest.main()
