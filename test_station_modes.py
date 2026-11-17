"""Station identity, exclusive modes, launcher, HDMI and virtual AX.25 client tests."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from aprs_bbs import AX25PBBS, validate_bbs_config
from aprs_protocol import KissDecoder, decode_ax25
from aprs_service import APRSService
from service_config import ServiceConfig
from test_bbs_v24 import Clock, FakeTNC, bbs_cfg
from web_panel import WebPanel


class IdentityTests(unittest.TestCase):
    def test_legacy_migration_shared_call_ssids_and_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'config.json'
            path.write_text(json.dumps({'igate':{'call':'OK1ABC-12'},'digi':{'call':'OK1ABC-4'},'bbs':{'call':'OK1ABC-9'}}))
            c=ServiceConfig(path).load_or_create()
            self.assertEqual(c.data['station']['call'],'OK1ABC')
            self.assertEqual(c.data['station']['igate_ssid'],12)
            self.assertEqual(c.data['station']['digi_ssid'],4)
            self.assertEqual(c.data['bbs']['call'],'OK1ABC-9')
            token=c.secrets['admin_token']
            c.update({},passcode='12345')
            c.update({'station':{'call':'OK2XYZ','bbs_ssid':8,'client_ssid':7}})
            self.assertEqual(c.secrets['web_username'],'OK2XYZ')
            self.assertEqual(c.secrets['admin_token'],token)
            self.assertEqual(c.secrets['igate_passcode'],'')
            self.assertEqual(c.data['igate']['call'],'OK2XYZ-12')
            self.assertEqual(c.data['digi']['call'],'OK2XYZ-4')
            self.assertEqual(c.data['bbs']['call'],'OK2XYZ-8')
            self.assertEqual(ServiceConfig(path).load_or_create().secrets['web_username'],'OK2XYZ')
            for changes in ({'call':'OK2XYZ-1'},{'bbs_ssid':True},{'bbs_ssid':7},{'call':'<script>'}):
                with self.subTest(changes=changes),self.assertRaises(ValueError):c.update({'station':changes})


class ModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.config=ServiceConfig(Path(self.tmp.name)/'config.json').load_or_create()
        self.service=APRSService(self.config)
        self.attach()

    def attach(self):
        self.tnc=FakeTNC()
        self.tnc.join=lambda timeout:None
        self.service.reader=self.tnc
        self.service.radio_ready=True
        self.service.serial_stop=threading.Event()

    def tearDown(self):
        for component in ('bbs','secondary','alerts','archive','messages','journal'):
            getattr(self.service,component).close()
        self.tmp.cleanup()

    def test_mode_switch_cancels_aprs_and_blocks_reverse_activation(self):
        s=self.service
        s._execute('digi_on',{'confirm':True})
        pending=s.messages.compose('OK1ABC-7','pending','')
        s._execute('mode_set',{'mode':'bbs','confirm':True})
        self.assertFalse(s.digi.enabled)
        self.assertFalse(self.tnc.digi_allowed.is_set())
        self.assertTrue(s.serial_stop.is_set())
        self.assertIsNone(s.reader)
        self.assertEqual(s.messages.snapshot()['outbox'][0]['status'],'interrupted')
        self.assertFalse(s.messages.auto_ack)
        self.attach()
        s._execute('bbs_on',{'confirm':True,'confirm_channel':True})
        for action in ('igate_on','digi_on','message_send','tx_test','isrf_on','position_send'):
            with self.subTest(action=action),self.assertRaises(ValueError):s._execute(action,{'confirm':True})
        self.assertTrue(s.bbs.active)
        s._execute('mode_set',{'mode':'aprs','confirm':True})
        self.assertFalse(s.bbs.active)
        self.assertFalse(self.tnc.bbs_allowed.is_set())
        self.assertEqual(s.station_snapshot()['mode'],'aprs')
        self.assertTrue(self.config.data['display']['enabled'])
        s._execute('mode_set',{'mode':'off','confirm':True})
        self.assertFalse(self.config.data['display']['enabled'])
        with self.assertRaises(ValueError):s._execute('bbs_on',{'confirm':True,'confirm_channel':True})

    def test_mode_and_identity_changes_cannot_bypass_controller(self):
        with self.assertRaises(ValueError):self.service._execute('mode_set',{'mode':'bbs'})
        with self.assertRaises(ValueError):self.service._execute('save',{'config':{'station':{'mode':'bbs'}}})
        self.service._execute('station_save',{'station':{'call':'OK2XYZ','bbs_ssid':8,'client_ssid':7}})
        self.assertEqual(self.service.config.secrets['web_username'],'OK2XYZ')
        self.assertEqual(self.service.messages.own_call,'OK2XYZ-10')
        self.assertIsNone(self.service.reader)
        self.assertFalse(self.service.bbs.active)

    def test_station_http_auth_dynamic_username_and_private_hdmi_modes(self):
        panel=WebPanel(self.service.state,self.service,admin_token=self.config.secrets['admin_token'])
        panel.start(port=0)
        root=f'http://127.0.0.1:{panel.port}'
        try:
            with self.assertRaises(HTTPError) as err:urlopen(root+'/api/station')
            self.assertEqual(err.exception.code,403)
            key=self.config.secrets['admin_token']
            with urlopen(root+'/api/station?admin='+key) as response:self.assertEqual(json.load(response)['call'],'OK5TVR')
            self.service._execute('station_save',{'station':{'call':'OK2XYZ'}})
            payload=json.dumps({'username':'OK2XYZ','token':key}).encode()
            with urlopen(Request(root+'/api/login',data=payload,headers={'Content-Type':'application/json'})) as response:
                self.assertEqual(response.status,200)
            with urlopen(root+'/api/local-display') as response:
                display=json.load(response)
            self.assertEqual(display['call'],'OK2XYZ')
            self.assertNotIn(key,json.dumps(display))
            self.assertNotIn('messages',display['bbs'])
            self.service._execute('mode_set',{'mode':'bbs','confirm':True})
            with urlopen(root+'/api/local-display') as response:
                display=json.load(response)
            self.assertEqual(display['mode'],'bbs')
            self.assertEqual(display['bbs']['call'],'OK2XYZ-8')
            self.assertIn('stats',display['bbs'])
            self.assertNotIn('messages',display['bbs'])
        finally:panel.close()

    def test_client_cancel_does_not_start_server(self):
        self.service._execute('mode_set',{'mode':'bbs','confirm':True})
        self.attach()
        self.service._execute('bbs_client_connect',{'remote':'OK1ABC-8','confirm':True,'confirm_channel':True})
        self.assertTrue(self.service.bbs.snapshot()['connecting'])
        self.assertEqual(self.service.bbs.local_call,'OK5TVR-7')
        self.service._execute('bbs_disconnect',{'confirm':True})
        self.assertFalse(self.service.bbs.active)
        self.assertFalse(self.tnc.bbs_allowed.is_set())


class ClientTests(unittest.TestCase):
    def test_two_virtual_tncs_connect_help_and_disconnect(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock=Clock()
            config=bbs_cfg();config['call']='OK1ABC-8'
            server=AX25PBBS(Path(tmp)/'server.sqlite3',config,clock)
            client=AX25PBBS(Path(tmp)/'client.sqlite3',bbs_cfg(),clock)
            wire=[]
            def send_from(sender,target):
                return lambda payload,cat:(wire.append((sender,target,payload,cat)) or True)
            cs=send_from(client,server);ss=send_from(server,client)
            def pump():
                for _ in range(150):
                    while wire:
                        sender,target,payload,cat=wire.pop(0)
                        sender.on_tx_written(cat)
                        raw=KissDecoder().feed(payload)[0][1:]
                        target.on_frame(decode_ax25(raw),ss if target is server else cs)
                    client.tick(cs);server.tick(ss)
                    if not wire:return
                self.fail('Virtual link did not settle')
            try:
                server.start();client.connect('OK1ABC-8','OK5TVR-7',cs);pump()
                self.assertTrue(client.snapshot()['connected'])
                self.assertIn('Type H',client.console)
                client.send_text('H');pump()
                self.assertIn('LN [page]',client.console)
                self.assertEqual(server.session.remote,'OK5TVR-7')
                client.send_text('Q');pump()
                self.assertFalse(client.snapshot()['connected'])
                self.assertIsNone(server.session)
                self.assertEqual(client.snapshot()['last_disconnect'],'remote_disconnect')
            finally:client.close();server.close()

    def test_connect_retries_are_bounded_and_no_incoming_shell_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock=Clock();client=AX25PBBS(Path(tmp)/'client.sqlite3',bbs_cfg(),clock)
            sent=[]
            send=lambda raw,cat:(sent.append(cat) or True)
            try:
                client.connect('OK1ABC-8','OK5TVR-7',send)
                for _ in range(6):
                    if client.session is None:break
                    client.on_tx_written(sent[-1]);clock.step(13);client.tick(send)
                self.assertIsNone(client.session)
                self.assertEqual(client.last_disconnect,'connect_timeout')
                self.assertEqual(len(sent),5)
                with self.assertRaises(ValueError):client.send_text('H')
            finally:client.close()


class LauncherScriptTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node.js required')
    def test_launcher_navigation_is_read_only_and_terminal_is_bounded(self):
        source=re.findall(r'<script>(.*?)</script>',Path(__file__).with_name('web_station.html').read_text(),re.S)[0]
        harness=r'''
        const assert=require('node:assert/strict'),vm=require('node:vm');
        class Element{
          constructor(id=''){this.id=id;this.value='';this.textContent='';this.children=[];this.style={};this.dataset={};this.listeners={};this.classes=new Set();this.classList={toggle:(n,v)=>v?this.classes.add(n):this.classes.delete(n)};}
          querySelector(){return this.children[0]||null;}appendChild(c){c.parentElement=this;this.children.push(c);}
          addEventListener(k,f){this.listeners[k]=f;}remove(){this.parentElement.children=[];}
        }
        const nodes=new Map(),get=id=>{if(!nodes.has(id))nodes.set(id,new Element(id));return nodes.get(id);};
        const frames=()=>[...nodes.values()].flatMap(n=>n.children);
        const mode='aprs',calls=[],navigations=[];
        const state=()=>({call:'OK5TVR',mode,ip:'192.0.2.2',tnc_connected:true,tnc_port:'TEST'});
        const history=[{time:'12:01',source:'OK1ABC-7',destination:'APRS',path:'WIDE1-1',kind:'RAW',payload:'<script>test</script>',summary:'Decoded packet'},
          {time:'12:00',source:'OK2XYZ',destination:'APRS',kind:'Status',payload:'Hello'}];
        const document={getElementById:get,createElement:()=>new Element(),querySelectorAll:()=>[]};
        const context={document,window:{OK5TVRLocale:{language:'cs'},addEventListener:()=>{}},URLSearchParams,AbortController,setTimeout,clearTimeout,setInterval:()=>{},Date,confirm:()=>{throw Error('Navigation must not ask to switch mode');},console,
          location:{search:'?admin=test-key',hash:'',pathname:'/app',assign:url=>navigations.push(url)},
          fetch:async(path,opts)=>{if(opts&&opts.method==='POST'){calls.push(JSON.parse(opts.body));throw Error('Unexpected POST');}
          return {ok:true,json:async()=>path.startsWith('/api/state?')?{history}:state()};}};
        (async()=>{vm.createContext(context);vm.runInContext(SOURCE,context);await new Promise(setImmediate);
          assert.equal(calls.length,0);
          assert(get('open-aprs').classes.has('on'));assert(!get('open-bbs').classes.has('on'));
          context.select('bbs');context.select('settings');context.select('aprs');
          assert.deepEqual(navigations,['/bbs?admin=test-key','/settings?admin=test-key','/aprs?admin=test-key']);
          assert.equal(calls.length,0,'All launcher buttons must be navigation-only');
          assert(get('open-aprs').classes.has('on'),'Navigation must not change status colors');
          const text=get('terminal-output').textContent;
          assert(text.includes('<script>test</script>'),'Packet markup is rendered as literal text');
          assert(text.indexOf('12:00')<text.indexOf('12:01'),'Terminal is chronological');
          get('terminal-pause').checked=true;context.renderTerminal({history:[]});assert.equal(get('terminal-output').textContent,text);
          get('terminal-pause').checked=false;
          context.renderTerminal({history:Array.from({length:200},(_,i)=>({time:String(i),source:'OK1ABC',payload:'frame'}))});
          assert(get('terminal-count').textContent.includes('150 / 150'));
          await get('terminal-clear').onclick();assert(!get('terminal-output').textContent.includes('12:01'));
          assert.equal(calls.length,0,'Clearing the view must not mutate service history');
          assert.equal(history.length,2);
          assert.equal(get('station-call').textContent,'OK5TVR');assert.equal(get('station-ip').textContent,'IP: 192.0.2.2');
        })().catch(e=>{console.error(e);process.exitCode=1;});
        '''
        run=subprocess.run(['node','-e',harness.replace('SOURCE',json.dumps(source))],text=True,capture_output=True,timeout=15)
        self.assertEqual(run.returncode,0,run.stderr)


if __name__=='__main__':unittest.main()
