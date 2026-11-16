"""Exercise real BBS page JS with nonempty mail, without RF or a browser."""
from pathlib import Path
import re
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node.js required')
class BBSWebMailTests(unittest.TestCase):
    def test_mail_render_translation_and_delete(self):
        html = Path(__file__).with_name('web_bbs.html').read_text(encoding='utf-8')
        code = '\n'.join(re.findall(r'<script>(.*?)</script>', html, re.S))
        harness = r'''
        const assert=require('node:assert/strict'),vm=require('node:vm');
        class Element {
          constructor(){this.textContent='';this.children=[];this.listeners={};}
          appendChild(child){this.children.push(child);}
          replaceChildren(...children){this.children=children;}
          addEventListener(name,listener){this.listeners[name]=listener;}
        }
        const elements=new Map();
        const element=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
        let mail=[{id:1,created_utc:'2026-11-16',sender:'OK1ABC-7',recipient:'ALL',subject:'Test',body:'Hello'}];
        const requests=[];
        const context={document:{getElementById:element,createElement:()=>new Element()},
          window:{OK5TVRLocale:{language:'en',tr:text=>text==='Smazat'?'Delete':text},addEventListener:()=>{}},
          URLSearchParams,location:{search:''},confirm:()=>true,setInterval:()=>{},console,
          fetch:async(path,options)=>{
            if(options && options.method==='POST'){
              requests.push(JSON.parse(options.body));mail=[];
              return {ok:true,json:async()=>({ok:true,result:{deleted:true}})};
            }
            return {ok:true,json:async()=>path==='/api/config'?{bbs:{}}:
              {active:false,mail_count:mail.length,messages:mail}};
          }};
        (async()=>{
          vm.runInNewContext(SOURCE,context);
          await new Promise(setImmediate);
          assert.equal(element('err').textContent,'','Mailbox refresh must not throw');
          const rows=element('messages').children;
          assert.equal(rows.length,1,'Stored mail must render');
          assert.equal(rows[0].children[4].textContent,'Test');
          const button=rows[0].children[6].children[0];
          assert.equal(button.textContent,'Delete');
          await button.listeners.click();
          assert.equal(requests.length,1);
          assert.deepEqual(requests[0],{action:'bbs_delete',id:1,confirm:true});
          assert.equal(element('messages').children.length,0,'Deletion refresh must remove the row');
          assert.equal(element('err').textContent,'');
        })().catch(error=>{console.error(error);process.exitCode=1;});
        '''
        import json
        result = subprocess.run(['node', '-e', harness.replace('SOURCE', json.dumps(code))],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
