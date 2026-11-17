"""PBBS mail migration, RF workflows, permissions and local-only web posting."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from aprs_bbs import BBSStore
import test_bbs_v24 as base
from test_bbs_v24 import bbs_cfg
from web_panel import WebPanel


class MailStoreTests(unittest.TestCase):
    def test_existing_database_migrates_and_read_state_persists_per_ssid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bbs.sqlite3'
            db=sqlite3.connect(path)
            db.execute('CREATE TABLE bbs_mail (id INTEGER PRIMARY KEY, created_utc TEXT NOT NULL, sender TEXT NOT NULL, recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL)')
            db.execute("INSERT INTO bbs_mail VALUES (42,'old','OK1ABC-7','OK2XYZ-9','Saved','Keep me')")
            db.commit();db.close()
            store=BBSStore(path)
            self.assertEqual(store.list_for('OK2XYZ-9',unread=True)[0]['id'],42)
            self.assertIsNone(store.read_for(42,'OK2XYZ-8'))
            self.assertEqual(store.read_for(42,'OK2XYZ-9')['body'],'Keep me')
            self.assertEqual(store.list_for('OK2XYZ-9',unread=True),[])
            store.close()
            store=BBSStore(path)
            self.assertTrue(store.admin_list()[1][0]['recipient_read'])
            self.assertTrue(store.delete_for(42,'OK2XYZ-9'))
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM bbs_reads').fetchone()[0],0)
            store.close()

    def test_pagination_public_read_state_and_delete_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=BBSStore(Path(tmp)/'bbs.sqlite3',max_messages=50)
            try:
                for i in range(55):store.post('OK1ABC-7','ALL',f'Title {i}','body')
                first=store.list_for('OK2XYZ-9',limit=15)
                second=store.list_for('OK2XYZ-9',limit=15,offset=15)
                self.assertFalse({m['id'] for m in first}&{m['id'] for m in second})
                ident=first[0]['id']
                store.read_for(ident,'OK2XYZ-9')
                self.assertFalse(store.list_for('OK2XYZ-9',unread=True)[0]['id']==ident)
                self.assertEqual(store.list_for('OK3AAA',unread=True)[0]['id'],ident)
                self.assertFalse(store.delete_for(ident,'OK2XYZ-9'))
                self.assertTrue(store.delete_for(ident,'OK1ABC-7'))
                count,items=store.admin_list(offset=45)
                self.assertEqual(count,49)
                self.assertEqual(len(items),4)
                self.assertLessEqual(store.db.execute('SELECT COUNT(*) FROM bbs_reads').fetchone()[0],50)
            finally:store.close()


class MailRFTests(unittest.TestCase):
    setUp=base.PbbsEngineTests.setUp
    tearDown=base.PbbsEngineTests.tearDown
    connect=base.PbbsEngineTests.connect
    parsed_output=base.PbbsEngineTests.parsed_output
    def test_full_message_reply_abort_read_and_delete(self):
        self.connect();link=self.pbbs.session
        text='\n'.join(f'line {i}' for i in range(30))+'\nLAST LINE'
        ident=self.pbbs.store.post('OK2XYZ-9',link.remote,'Long mail',text)
        link.output.clear();self.pbbs._command(f'R {ident}')
        self.assertIn(b'LAST LINE',link.output)
        self.assertNotIn(b'truncated',link.output)
        self.assertEqual(self.pbbs.store.list_for(link.remote,unread=True),[])
        self.pbbs._command(f'RE {ident}')
        self.assertEqual((link.to,link.subject,link.stage),('OK2XYZ-9','Re: Long mail','body'))
        self.pbbs._command('A reply');self.pbbs._command('/ABORT')
        self.assertEqual(link.stage,'command')
        self.assertEqual(self.pbbs.snapshot()['mail_count'],1)
        link.output.clear();self.pbbs._command(f'RE {ident}')
        self.pbbs._command('A reply');self.pbbs._command('/EX')
        self.assertEqual(self.pbbs.store.list_for('OK2XYZ-9')[0]['subject'],'Re: Long mail')
        self.pbbs._command(f'K {ident}')
        self.assertIsNotNone(self.pbbs.store.admin_get(ident))
        self.pbbs._command(f'K {ident} YES')
        self.assertIsNone(self.pbbs.store.admin_get(ident))

    def test_rf_pages_and_private_message_access(self):
        self.connect();link=self.pbbs.session
        for i in range(32):self.pbbs.store.post('OK2XYZ-9','ALL',f'Mail {i}','text')
        link.output.clear();self.pbbs._command('L')
        self.assertIn(b'More: L 2 or N',link.output)
        self.assertIn(b'Mail 31',link.output)
        link.output.clear();self.pbbs._command('N')
        self.assertIn(b'L page 2',link.output)
        self.assertNotIn(b'Mail 31',link.output)
        secret=self.pbbs.store.post('OK2XYZ-9','OK3AAA','Secret','Not yours')
        link.output.clear();self.pbbs._command(f'RE {secret}')
        self.assertIn(b'Message not available.',link.output)
        self.assertEqual(link.stage,'command')
        self.pbbs._command(f'K {secret} YES')
        self.assertIsNotNone(self.pbbs.store.admin_get(secret))

    def test_line_editing_crlf_blank_lines_and_overflow(self):
        self.connect();link=self.pbbs.session
        self.pbbs._accept_text(b'SB\r\nDraft\r\n  indented\r\n\r\nlastx\x08!\r\n/EX\r\n')
        saved=self.pbbs.store.admin_list()[1][0]
        self.assertEqual(saved['body'],'  indented\n\nlast!')
        self.pbbs._accept_text(b'SB\r')
        self.pbbs._accept_text(b'X'*101+b'\r')
        self.assertEqual(link.stage,'subject')
        self.pbbs._accept_text(b'/ABORT\r')
        self.assertEqual(link.stage,'command')
        self.assertEqual(self.pbbs.snapshot()['mail_count'],1)

    def test_complete_message_survives_kiss_frames_and_sequence_wrap(self):
        self.pbbs.start()
        self.pbbs.on_frame(base.rx(),self.send)
        self.pbbs.on_tx_written(self.out[-1][1])

        def drain():
            result=bytearray()
            for _ in range(40):
                self.pbbs.tick(self.send)
                pending=self.pbbs.session.unacked
                if pending is None:
                    if not self.pbbs.session.output:return bytes(result)
                    self.fail('Output was not queued')
                packet=self.parsed_output()
                self.assertEqual(packet.raw_info[0],0xF0)
                result.extend(packet.raw_info[1:])
                self.pbbs.on_tx_written(self.out[-1][1])
                nr=(pending['ns']+1)&7
                self.pbbs.on_frame(base.rx(control=0x01|(nr<<5)),self.send)
            self.fail('BBS output did not finish')

        drain()  # Deliver and acknowledge the welcome text first.
        body='A'*780+'\nEND OF FULL MESSAGE'
        ident=self.pbbs.store.post('OK2XYZ-9','OK1ABC-7','Long message',body)
        nr=self.pbbs.session.vs
        self.pbbs.on_frame(base.rx(control=nr<<5,text=b'\xF0R '+str(ident).encode()+b'\r'),self.send)
        received=drain()
        self.assertIn(body.replace('\n','\r').encode(),received)
        self.assertGreater(self.pbbs.counters['ack_i'],8)  # Modulo-8 wrapped.
        self.assertIsNone(self.pbbs.session.unacked)

    def test_diagnostics_exposes_retries_and_disconnect_reason(self):
        self.connect()
        self.assertTrue(self.pbbs.snapshot()['waiting_ack'])
        self.assertEqual(self.pbbs.snapshot()['retries'],0)
        self.clock.step(181);self.pbbs.tick(self.send)
        self.assertEqual(self.pbbs.snapshot()['last_disconnect'],'idle_timeout')


class MailWebServiceTests(unittest.TestCase):
    setUp=base.PbbsServiceTests.setUp
    tearDown=base.PbbsServiceTests.tearDown
    def test_local_web_post_reply_validation_and_no_rf_tx(self):
        self.service._execute('bbs_save',{'bbs':bbs_cfg()})
        post={'recipient':'OK1ABC-7','subject':'Hello','body':'Local mail','confirm':True}
        with self.assertRaises(ValueError):self.service._execute('bbs_post',{**post,'confirm':False})
        number=self.service._execute('bbs_post',post)['id']
        self.assertEqual(self.service.bbs.store.admin_get(number)['sender'],'OK5TVR-8')
        received=self.service.bbs.store.post('OK2XYZ-9','OK5TVR-8','Question','Test')
        reply=self.service._execute('bbs_post',{**post,'reply_to':received})['id']
        self.assertEqual(self.service.bbs.store.admin_get(reply)['recipient'],'OK2XYZ-9')
        for bad in ({'body':'x'*801},{'subject':'Bad\nheader'},{'body':'Příliš'},{'recipient':'INVALID-CALL'}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                self.service._execute('bbs_post',{**post,**bad})
        self.assertFalse(self.service.bbs.active)
        self.assertEqual(self.tnc.tx,[])
        self.assertFalse(self.tnc.bbs_allowed.is_set())

    def test_admin_mail_pages_and_post_authentication(self):
        for i in range(55):self.service.bbs.store.post('OK1ABC-7','ALL',f'Test {i}','Body')
        panel=WebPanel(self.service.state,operator=self.service,admin_token='test-admin')
        panel.start(port=0)
        try:
            root=f'http://127.0.0.1:{panel.port}'
            with urlopen(root+'/api/bbs?admin=test-admin&offset=50') as response:
                page=json.load(response)
            self.assertEqual(len(page['messages']),5)
            self.assertEqual(page['page_offset'],50)
            for query in ('-1','bad','2001'):
                with self.assertRaises(HTTPError) as err:urlopen(root+'/api/bbs?admin=test-admin&offset='+query)
                self.assertEqual(err.exception.code,400)
            req=Request(root+'/api/control',data=json.dumps({'action':'bbs_post','confirm':True,'recipient':'ALL','subject':'Test','body':'body'}).encode(),headers={'Content-Type':'application/json','X-APRS-CSRF':'1'},method='POST')
            with self.assertRaises(HTTPError) as err:urlopen(req)
            self.assertEqual(err.exception.code,403)
            self.assertEqual(self.service.bbs.snapshot()['mail_count'],55)
        finally:panel.close()


if __name__=='__main__':unittest.main()
