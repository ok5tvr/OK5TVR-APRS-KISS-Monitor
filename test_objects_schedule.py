"""Saved object transport, validation and deadline regressions."""
import datetime as dt
import json
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from types import SimpleNamespace
from aprs_objects import validate_entries, ObjectSchedule
from aprs_service import APRSService
from aprs_serial import SerialReader
from aprs_tcp import TCPKissReader
from aprs_features import APRSISClient
from aprs_protocol import KissDecoder, decode_ax25
from service_config import ServiceConfig


def entry(**kwargs):
    return validate_entries([dict(name='TEST',lat=49.75,lon=13.25,**kwargs)])[0]


class ScheduleTests(unittest.TestCase):
    def test_validation(self):
        for values in ([entry()]*6,[entry(),entry()], [dict(name='bad:name')],
                [dict(name='TEST',lat=float('nan'))],[dict(name='TEST',schedule='times',times=['25:00'])],
                [dict(name='TEST',interval_minutes=0)],[dict(name='TEST',comment='ž')]):
            with self.subTest(values=values),self.assertRaises(ValueError):validate_entries(values)
        self.assertEqual(entry(path='DIRECT')['path'],'')
        self.assertEqual(entry(transport='inet',schedule='times',times=['08:00','08:00'])['times'],['08:00'])

    def test_intervals_paced_and_no_replay(self):
        entries=[entry(schedule='interval',interval_minutes=1),dict(entry(schedule='interval',interval_minutes=1),name='SECOND')]
        s=ObjectSchedule();sent=[]
        send=lambda i,e:sent.append(i) or 'queued'
        s.tick(entries,send,now=1000);self.assertEqual(sent,[])
        s.start(entries,now=0);s.tick(entries,send,now=59);self.assertEqual(sent,[])
        s.tick(entries,send,now=60);s.tick(entries,send,now=61);self.assertEqual(sent,[0])
        s.tick(entries,send,now=65);self.assertEqual(sent,[0,1])
        s.tick(entries,send,now=10000);s.tick(entries,send,now=10000);self.assertEqual(sent,[0,1,0])
        s.stop();s.tick(entries,send,now=11000);self.assertEqual(len(sent),3)

    def test_daily_once_including_dst_repeat_and_transport_failure(self):
        entries=[entry(schedule='times',times=['08:00'])];s=ObjectSchedule();s.start(entries,0)
        sent=[]
        def send(i,e):sent.append(i);raise ValueError('offline')
        wall=dt.datetime(2026,11,17,8,0)
        s.tick(entries,send,now=0,wall=wall);s.tick(entries,send,now=30,wall=wall)
        self.assertEqual(sent,[0]);self.assertEqual(s.status[0],'offline')
        s.tick(entries,send,now=86400,wall=wall+dt.timedelta(days=1));self.assertEqual(sent,[0,0])


class ServiceObjectsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'config.json'
        self.s=APRSService(ServiceConfig(self.path).load_or_create())
    def tearDown(self):
        for name in ('bbs','secondary','alerts','archive','messages','journal'):getattr(self.s,name).close()
        self.temp.cleanup()
    def test_saved_transport_and_mode_guards(self):
        sent=[];self.s.reader=SimpleNamespace(objects_epoch=0,send=lambda payload,category:sent.append((payload,category)) or True)
        self.s.radio_ready=True
        self.s._execute('objects_save',{'entries':[entry(path='DIRECT')]})
        with self.assertRaises(ValueError):self.s._execute('object_slot_send',{'index':0})
        self.s._execute('object_slot_send',{'index':0,'confirm':True})
        frame=KissDecoder().feed(sent[0][0])[0][1:];packet=decode_ax25(frame)
        self.assertEqual(packet.source,'OK5TVR-10');self.assertIn(b';TEST',frame)
        internet=[]
        self.s.igate_client=SimpleNamespace(enqueue_local=lambda line,kind:internet.append((line,kind)) or True)
        self.s._execute('objects_save',{'entries':[entry(transport='inet')]})
        self.s._execute('object_slot_send',{'index':0,'confirm':True})
        self.assertEqual(len(sent),1);self.assertTrue(internet[0][0].startswith('OK5TVR-10>APRS,TCPIP*:;TEST'))
        self.assertTrue(internet[0][1].startswith('object:'))
        self.s.operating_mode='bbs'
        with self.assertRaises(ValueError):self.s._execute('object_slot_send',{'index':0,'confirm':True})
        with self.assertRaises(ValueError):self.s._execute('objects_start',{'confirm':True})
        self.s.reader=None;self.s.igate_client=None
    def test_config_survives_restart_but_schedule_does_not(self):
        self.s._execute('objects_save',{'entries':[entry(schedule='interval')]})
        self.s._execute('objects_start',{'confirm':True});self.assertTrue(self.s.objects.active)
        self.s._execute('objects_save',{'entries':[entry()]});self.assertFalse(self.s.objects.active)
        self.assertEqual(ServiceConfig(self.path).load_or_create().data['object_slots']['entries'][0]['name'],'TEST')
        with self.assertRaises(ValueError):self.s._execute('objects_save',{'entries':[entry()]*6})
        self.assertEqual(len(self.s.config.data['object_slots']['entries']),1)
    def test_stale_rf_frames_rejected_before_queue(self):
        for reader in (SerialReader('FAKE',115200,queue.Queue(),threading.Event(),1),TCPKissReader('localhost',8001,queue.Queue(),threading.Event(),1)):
            reader.connected=True;reader.objects_epoch=7
            self.assertFalse(reader.send(b'x',category='object_slot:0:6'))
            self.assertTrue(reader.send(b'x',category='object_slot:0:7'))
        self.s.objects.start([entry()],0);epoch=self.s.objects.epoch
        self.s._execute('objects_stop',{});self.assertNotEqual(epoch,self.s.objects.epoch)

class ObjectBrowserLogicTests(unittest.TestCase):
    def test_editor_loads_selects_and_preserves_unsaved_fields(self):
        import re
        import subprocess
        source=re.findall(r'<script>([\s\S]*?)</script>',Path(__file__).with_name('web_objects.html').read_text())[0]
        harness=r'''
const vm=require('vm'),assert=require('assert');
class Element {
 constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.value='';this.textContent='';this.href='/';if(tag==='select')Object.defineProperty(this,'type',{get:()=> 'select-one'});}
 append(...items){this.children.push(...items);}replaceChildren(...items){this.children=items;}
}
const ids={};const doc={getElementById:id=>ids[id]||(ids[id]=new Element()),createElement:t=>new Element(t),querySelectorAll:()=>[]};
let requests=[];
const data={active:false,device_time:'2026-11-17T12:00:00+01:00',entries:[{name:'FIRST',lat:49,lon:13,comment:'',symbol_table:'/',symbol:'r',transport:'rf',path:'WIDE1-1',alive:true,enabled:true,schedule:'manual',interval_minutes:30,times:[]}],status:{}};
const context={document:doc,window:{OK5TVRLocale:{language:'cs'},addEventListener:()=>{}},location:{pathname:'/settings/objects',search:'?admin=TOKEN'},URLSearchParams,confirm:()=>true,setInterval:()=>{},fetch:async(url,opts)=>{requests.push({url,opts});return {ok:true,json:async()=>opts?.method==='POST'?{ok:true,result:'saved'}:data};}};
vm.createContext(context);vm.runInContext(SOURCE,context);
setImmediate(async()=>{try{
 assert.equal(ids.entries.children.length,1,ids.notice?.textContent);
 const fields=ids.entries.children[0].children[1];assert(fields.children.some(l=>l.children[0].tag==='select'));
 const name=fields.children[0].children[0];name.value='EDIT';name.oninput();
 await vm.runInContext('refresh()',context);assert.equal(name.value,'EDIT');
 for(let i=0;i<5;i++)ids.add.onclick();assert.equal(ids.entries.children.length,5);assert.equal(ids.add.disabled,true);
 ids.start.onclick();assert.equal(requests.filter(r=>r.opts?.method==='POST').length,0);
 ids.save.onclick();await new Promise(resolve=>setImmediate(resolve));
 const body=JSON.parse(requests.find(r=>r.opts?.method==='POST').opts.body);assert.equal(body.action,'objects_save');assert.equal(body.entries.length,5);assert.equal(body.entries[0].name,'EDIT');
 console.log('Editor OK');
 }catch(e){console.error(e);process.exitCode=1;}});
'''.replace('SOURCE',json.dumps(source))
        result=subprocess.run(['node','-e',harness],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
