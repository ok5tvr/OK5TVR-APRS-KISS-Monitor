"""Shared navigation: authentication links, active page and mobile keyboard controls."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from web_views import APRS_ROUTES, BBS_ROUTES, SETTINGS_ROUTES


class SharedShellTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node.js needed for browser logic checks')
    def test_active_navigation_auth_and_mobile_controls_without_radio_commands(self):
        source=Path(__file__).with_name('web_shell.js').read_text()
        routes=['/app']+[r for r,_,_ in APRS_ROUTES+BBS_ROUTES+SETTINGS_ROUTES]
        script=r'''
const assert=require('node:assert/strict'),vm=require('vm');
class Node {
 constructor(route){this.dataset=route?{route}:{};this.attrs={};this.events={};this.style={setProperty:()=>{}};this.classList={values:new Set(),add(n){this.values.add(n)},remove(n){this.values.delete(n)},contains(n){return this.values.has(n)},toggle(n){if(this.values.has(n)){this.values.delete(n);return false;}this.values.add(n);return true;}};this.textContent=route||'';this.group={open:false};this.offsetHeight=76;}
 setAttribute(k,v){this.attrs[k]=v;}removeAttribute(k){delete this.attrs[k];}closest(){return this.group;}addEventListener(k,fn){this.events[k]=fn;}focus(){this.focused=true;}
}
const links=ROUTES.map(r=>new Node(r)),top=['/app','/aprs','/bbs','/settings'].map(r=>new Node(r));
const nodes={};for(const id of ['navigation-toggle','global-logout','global-call','global-clock','global-tnc','global-mode','global-ip','global-navigation'])nodes[id]=new Node();
const body=new Node();body.dataset={viewRole:'aprs-map',pageKind:'operation'};
const doc={body,documentElement:new Node(),getElementById:id=>nodes[id]||null,querySelectorAll:q=>q==='[data-route]'?[...links,...top]:q==='#station-sidebar [data-route]'||q==='#station-sidebar a'?links:q==='.global-links [data-route]'?top:[],querySelector:q=>links.find(l=>l.attrs['aria-current'])};
const events={},requests=[],loc={pathname:'/map',search:'?admin=SECRET',hash:'',origin:'http://localhost',replace:path=>loc.replaced=path};
const ctx={document:doc,window:{OK5TVRLocale:{language:'cs'},addEventListener:(n,f)=>events[n]=f},location:loc,URL,URLSearchParams,AbortController,setTimeout:()=>1,clearTimeout:()=>{},setInterval:()=>{},confirm:()=>true,fetch:async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>({call:'OK5TVR',tnc_connected:true,mode:'aprs',ip:'192.168.1.120'})}}};
vm.createContext(ctx);vm.runInContext(SOURCE,ctx);
setImmediate(async()=>{try{
 assert(links.every(l=>new URL(l.href,loc.origin).searchParams.get('admin')==='SECRET'));
 function active(route){assert.deepEqual(links.filter(l=>l.attrs['aria-current']).map(l=>l.dataset.route),[route]);}
 active('/map');assert(nodes['global-mode'].textContent.includes('APRS'));
 for(const [path,hash,query,target] of [['/objects','','','/objects'],['/operations','','','/operations'],['/messages','','','/messages'],['/aprs','#heard','','/aprs#heard'],['/aprs','','?tab=rx','/aprs#rx'],['/settings/advanced','','?tab=alerts','/settings/advanced?tab=alerts'],['/bbs','#bbs-mail','','/bbs#bbs-mail']]){
 loc.pathname=path;loc.hash=hash;loc.search=query;events['station:navigation']();active(target);
 assert(links.find(l=>l.dataset.route===target).group.open);
 }
 nodes['navigation-toggle'].events.click();assert(body.classList.contains('navigation-open'));assert.equal(nodes['navigation-toggle'].attrs['aria-expanded'],'true');
 events.keydown({key:'Escape'});assert(!body.classList.contains('navigation-open'));assert(nodes['navigation-toggle'].focused);
 nodes['navigation-toggle'].events.click();links[0].events.click();assert(!body.classList.contains('navigation-open'));
 assert(requests.every(r=>r.options.method!=='POST'));
 await nodes['global-logout'].events.click();assert.equal(loc.replaced,'/login');
 assert.equal(requests.filter(r=>r.options.method==='POST').length,1);assert.equal(requests.at(-1).url,'/api/logout');
 console.log('Shared sidebar, active routes, auth and mobile controls OK');
 }catch(e){console.error(e);process.exitCode=1;}});
'''.replace('ROUTES',json.dumps(routes)).replace('SOURCE',json.dumps(source))
        result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
